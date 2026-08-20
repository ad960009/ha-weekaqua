"""DataUpdateCoordinator and Schedule Engine for WeekAqua."""

from __future__ import annotations
import asyncio
from datetime import datetime, date, time, timedelta
import logging
import time as pytime
from typing import Any

from bleak import BleakClient
from bleak.exc import BleakError
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    establish_connection,
)

from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    DOMAIN,
    SERVICE_UUID,
    SERVICE_UUIDS,
    WRITE_CHAR_UUID,
    WRITE_CHAR_UUIDS,
    NOTIFY_CHAR_UUID,
    NOTIFY_CHAR_UUIDS,
    CONF_MAC,
    CONF_NAME,
    CONF_MODEL_CODE,
    CONF_KEEP_MOONLIGHT,
    CONF_SCHEDULE,
    CONF_SCHEDULE_INTERVAL,
    DEFAULT_SCHEDULE_INTERVAL,
)
from .protocol import WeekAquaProtocol, NormalizedSpectrum

_LOGGER = logging.getLogger(__name__)


def parse_time_str(time_str: str) -> tuple[int, int, int]:
    """Parse HH:MM, HH:MM:SS, or 24:00 string to (hour, minute, second)."""
    s = str(time_str).strip()
    if s in ("24:00", "24:0", "24"):
        return 24, 0, 0
    parts = [int(p) for p in s.split(":")]
    if len(parts) == 1:
        return max(0, min(24, parts[0])), 0, 0
    elif len(parts) == 2:
        return parts[0], parts[1], 0
    elif len(parts) >= 3:
        return parts[0], parts[1], parts[2]
    return 0, 0, 0


def _uuid_matches(discovered_uuid: str, target_uuid: str) -> bool:
    """
    [핵심 개선 3] 16비트 vs 128비트 UUID 정규화 매칭 유틸리티.
    Bleak가 128비트 전체 UUID를 리턴하고 target이 16비트 짧은 UUID(또는 그 반대)인 경우에도
    정확히 일치 여부를 판별합니다.
    """
    d_clean = str(discovered_uuid).lower().replace("-", "").strip()
    t_clean = str(target_uuid).lower().replace("-", "").strip()

    # 1. 완전 일치 (128bit vs 128bit 또는 16bit vs 16bit)
    if d_clean == t_clean:
        return True

    # 2. 16비트 축약형 비교 (표준 BLE 기본 Base UUID인 경우 4~8번째 자리 추출)
    d_short = d_clean[4:8] if (len(d_clean) == 32 and d_clean.startswith("0000") and d_clean.endswith("00805f9b34fb")) else d_clean
    t_short = t_clean[4:8] if (len(t_clean) == 32 and t_clean.startswith("0000") and t_clean.endswith("00805f9b34fb")) else t_clean

    if d_short == t_short:
        return True

    # 3. 부분 문자열 포함 매칭 (예: "ffe1"이 "0000ffe1-..."에 포함되어 있는지)
    if (len(t_clean) == 4 and t_clean in d_clean) or (len(d_clean) == 4 and d_clean in t_clean):
        return True

    return False


class WeekAquaCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator managing WeekAqua BLE communication and the Unlimited Dynamic Schedule Engine."""

    def __init__(self, hass: HomeAssistant, entry_data: dict[str, Any], entry: Any = None) -> None:
        """Initialize the WeekAqua coordinator."""
        self._entry = entry
        self.mac: str = entry_data[CONF_MAC]
        self.device_name: str = entry_data.get(CONF_NAME, "WeekAqua")
        self.model_code: str = entry_data.get(CONF_MODEL_CODE, "")
        self.keep_moonlight: bool = entry_data.get(CONF_KEEP_MOONLIGHT, True)
        self.schedule_interval: int = entry_data.get(CONF_SCHEDULE_INTERVAL, DEFAULT_SCHEDULE_INTERVAL)

        # Dynamic Unlimited Schedule Waypoints & Metadata (Persisted across restarts)
        self.schedule_points: list[dict[str, Any]] = entry_data.get(CONF_SCHEDULE, self._get_default_schedule())
        self.schedule_meta: dict[str, Any] = entry_data.get("schedule_meta", {})
        self.schedule_enabled: bool = True

        # Current live channel state (0.0 ~ 100.0)
        self.current_r: float = 0.0
        self.current_g: float = 0.0
        self.current_b: float = 0.0
        self.current_w: float = 0.0
        self.current_uv: float = 0.0
        self.current_v: float = 0.0
        self.current_fan: float = 50.0

        # Sensor state
        self.is_connected: bool = False
        self.power_kwh: float = 0.0
        self.total_power_pct: float = 0.0

        # Bleak Client & 독립적 락(Lock) 구조
        # [핵심 개선 1] 데드락 방지를 위해 연결 전용 락과 쓰기 전용 락 분리
        self._client: BleakClientWithServiceCache | BleakClient | None = None
        self._write_char_uuid: str | None = None
        self._notify_char_uuid: str | None = None
        self._connect_lock = asyncio.Lock()  # BLE 연결/해제 전용 락
        self._write_lock = asyncio.Lock()    # GATT 송신 직렬화 전용 락

        # [핵심 개선 2] BlueZ 크래시 및 과도한 재시도 방지를 위한 상태 플래그 & 쿨다운 타이머
        self._is_connecting: bool = False
        self._manual_disconnected: bool = False
        self._last_connect_attempt: float = 0.0
        self._connect_cooldown_sec: float = 15.0  # 15초 쿨다운으로 133 에러 방어15초간 자동 재시도 억제

        # [핵심 개선 4] 큐 누적 및 패킷 홍수 방지
        self._write_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=10)
        self._queue_task: asyncio.Task | None = None
        self._auto_disconnect_task: asyncio.Task | None = None
        self._auto_disconnect_delay: float = 60.0  # 60초 미사용 시 세션 자동 해제
        self._schedule_unsub: Any = None
        self._last_sent_spectrum: bytes | None = None
        self._last_rtc_sync_date: date | None = None

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{self.mac}",
            update_interval=timedelta(seconds=self.schedule_interval),
        )

    @property
    def display_name(self) -> str:
        """Return the user-specified name from Device Registry, Config Entry, or Bluetooth discovery."""
        if self._entry:
            dev_reg = dr.async_get(self.hass)
            device = dev_reg.async_get_device(identifiers={(DOMAIN, self.mac)})
            if device:
                if device.name_by_user:
                    return device.name_by_user
                if device.name and device.name not in ("WeekAqua Light", "WeekAqua"):
                    return device.name
            if self._entry.title and self._entry.title not in ("WeekAqua Light", "WeekAqua"):
                return self._entry.title
        return self.device_name or "WeekAqua Light"

    def _get_default_schedule(self) -> list[dict[str, Any]]:
        """Default natural 8-point smooth aquarium photoperiod."""
        return [
            {"time": "08:00", "r": 0.0, "g": 0.0, "b": 0.0, "w": 0.0, "uv": 0.0, "v": 0.0},
            {"time": "09:30", "r": 20.0, "g": 30.0, "b": 20.0, "w": 30.0, "uv": 10.0, "v": 10.0},
            {"time": "11:30", "r": 60.0, "g": 85.0, "b": 60.0, "w": 75.0, "uv": 40.0, "v": 30.0},
            {"time": "14:00", "r": 70.0, "g": 100.0, "b": 70.0, "w": 90.0, "uv": 50.0, "v": 40.0},
            {"time": "17:00", "r": 50.0, "g": 75.0, "b": 50.0, "w": 70.0, "uv": 30.0, "v": 20.0},
            {"time": "19:00", "r": 25.0, "g": 30.0, "b": 20.0, "w": 25.0, "uv": 10.0, "v": 5.0},
            {"time": "20:30", "r": 0.0, "g": 0.0, "b": 4.0, "w": 0.0, "uv": 0.0, "v": 0.0},
            {"time": "23:00", "r": 0.0, "g": 0.0, "b": 0.0, "w": 0.0, "uv": 0.0, "v": 0.0},
        ]

    async def async_setup(self) -> None:
        """Start background queue worker and initial sync."""
        self._queue_task = asyncio.create_task(self._process_write_queue())
        await self.async_refresh()

    async def async_unload(self) -> None:
        """Stop tasks and disconnect BLE client."""
        if self._auto_disconnect_task:
            self._auto_disconnect_task.cancel()
        if self._queue_task:
            self._queue_task.cancel()
        await self.async_disconnect()

    # --- BLE Connection & Write Queue ---

    def _is_4ch_rgb_uv(self) -> bool:
        """Detect if device is a 4-channel RGB/UV light (M800 Pro, M600, S-Series, T90, etc.)."""
        if self.model_code == "5746":
            return True
        if self.model_code in ("5748", "5749", "5750", "5751", "5752"):
            return False
        name = (self.device_name or "").upper()
        if any(w in name for w in ("6CH", "10CH", "MARINE", "CORAL", "A-SERIES", "A430")):
            return False
        return any(w in name for w in ("UV", "UVA", "RGB/UV", "RGB-UV", "RGB_UV", "M800", "M600", "M450", "M400", "M900", "M1200", "M-PRO", "M PRO", "S400", "S600", "S800", "S1200", "T90", "T60", "Z400", "Z600", "P600", "P800", "P900", "P1200")) or name.startswith("M")

    async def _ensure_connected(self, force: bool = False) -> bool:
        """
        [핵심 개선 1, 2] 안전한 비동기 연결 수립 및 중복 연결 방어 로직.
        - 이미 연결되어 유효한 쓰기 특성이 있으면 즉시 True 반환.
        - 다른 태스크가 이미 연결 시도 중이면 중복 시도를 막고 완료를 대기.
        - 최근 연결 실패 시 쿨다운(15초)을 두어 BlueZ 스택 과부하 및 133 에러 방지.
        """
        if force:
            self._manual_disconnected = False
        elif self._manual_disconnected:
            _LOGGER.debug("WeekAqua (%s) connect skipped - manual disconnect active.", self.mac)
            return False

        if self._client and self._client.is_connected and self._write_char_uuid:
            return True

        now = pytime.monotonic()
        if not force and (now - self._last_connect_attempt < self._connect_cooldown_sec):
            _LOGGER.debug(
                "WeekAqua (%s) connect attempt throttled (cooldown active: %.1fs remaining)",
                self.mac,
                self._connect_cooldown_sec - (now - self._last_connect_attempt)
            )
            return False

        async with self._connect_lock:
            # 락 획득 후 연결 상태 재검사 (Double-Checked Locking)
            if self._client and self._client.is_connected and self._write_char_uuid:
                return True

            if self._is_connecting:
                _LOGGER.debug("Connection already in progress for %s, skipping duplicate attempt.", self.mac)
                return False

            self._is_connecting = True
            self._last_connect_attempt = pytime.monotonic()

            try:
                ble_device = bluetooth.async_ble_device_from_address(self.hass, self.mac, connectable=True)
                if not ble_device:
                    # Fallback to non-connectable scanner cache
                    ble_device = bluetooth.async_ble_device_from_address(self.hass, self.mac, connectable=False)

                if not ble_device:
                    _LOGGER.warning(
                        "WeekAqua (%s) not found in Home Assistant Bluetooth scanner cache. "
                        "Verify device is powered on, within Bluetooth range, and not connected to phone app.",
                        self.mac
                    )
                    return False

                # 광고 데이터로부터 장치명 및 모델 코드 자동 보정
                if ble_device.name and (not self.device_name or self.device_name.startswith("WeekAqua (") or self.device_name == "WeekAqua Light"):
                    self.device_name = ble_device.name
                    _LOGGER.info("Auto-discovered BLE device name: %s for %s", self.device_name, self.mac)

                if not self.model_code:
                    try:
                        for s_info in bluetooth.async_discovered_service_info(self.hass):
                            if s_info.address.upper() == self.mac.upper() and s_info.manufacturer_data:
                                for m_id, m_data in s_info.manufacturer_data.items():
                                    hex_str = m_data.hex().upper()
                                    for target in ("5752", "5751", "5750", "5749", "5748", "5747", "5746", "5745"):
                                        if target in hex_str:
                                            self.model_code = target
                                            _LOGGER.info("Auto-discovered model code %s for %s", self.model_code, self.mac)
                                            break
                    except Exception:
                        pass

                _LOGGER.info("Connecting to WeekAqua BLE %s (%s)...", self.device_name, self.mac)
                self._client = await establish_connection(
                    BleakClientWithServiceCache,
                    ble_device,
                    self.device_name,
                    self._on_disconnected,
                    max_attempts=2,
                    use_services_cache=True,
                )
                self.is_connected = True
                _LOGGER.info("Connected to WeekAqua BLE %s (%s) successfully!", self.device_name, self.mac)

                # [핵심 개선 3] 16비트 vs 128비트 정규화 매칭을 통한 GATT 특성 탐색
                self._write_char_uuid = None
                self._notify_char_uuid = None

                # 1. 알려진 공식 UUID 목록 매칭
                for s in self._client.services:
                    for c in s.characteristics:
                        c_uuid_str = str(c.uuid)
                        for target_write in WRITE_CHAR_UUIDS:
                            if _uuid_matches(c_uuid_str, target_write):
                                self._write_char_uuid = c.uuid
                                break
                        for target_notify in NOTIFY_CHAR_UUIDS:
                            if _uuid_matches(c_uuid_str, target_notify):
                                self._notify_char_uuid = c.uuid
                                break

                # 2. Fallback: 쓰기 속성을 가진 특성 탐색
                if not self._write_char_uuid:
                    for s in self._client.services:
                        for c in s.characteristics:
                            if "write-without-response" in c.properties or "write" in c.properties:
                                self._write_char_uuid = c.uuid
                                _LOGGER.info("Resolved write characteristic by GATT property: %s (Service: %s)", c.uuid, s.uuid)
                                break
                        if self._write_char_uuid:
                            break

                if not self._write_char_uuid:
                    _LOGGER.error("No writable GATT characteristic found on %s (%s)", self.device_name, self.mac)
                    return False

                _LOGGER.info("Resolved GATT characteristics for %s: Write=%s, Notify=%s", self.mac, self._write_char_uuid, self._notify_char_uuid)
                self.async_set_updated_data(self._build_data())

                # Device Registry 동기화 (모델명 및 블루투스 연결자)
                try:
                    dev_reg = dr.async_get(self.hass)
                    device = dev_reg.async_get_device(identifiers={(DOMAIN, self.mac)})
                    if device:
                        dev_reg.async_update_device(
                            device_id=device.id,
                            model=f"WeekAqua ({self.model_code or 'BLE'})",
                            merge_connections={(dr.CONNECTION_BLUETOOTH, self.mac)},
                        )
                except Exception as reg_err:
                    _LOGGER.debug("Device registry update on %s skipped: %s", self.mac, reg_err)

                # 스마트 플러그 전력 측정을 위한 Notify 구독
                if self._notify_char_uuid:
                    try:
                        await self._client.start_notify(self._notify_char_uuid, self._on_notify)
                        _LOGGER.info("Subscribed to GATT Notify: %s on %s", self._notify_char_uuid, self.mac)
                    except Exception as notify_err:
                        _LOGGER.debug("Notify subscription on %s skipped: %s", self.mac, notify_err)

                # 초기 RTC 동기화 및 MCU 상태 리셋 패킷 전송
                await self.enqueue_packet(WeekAquaProtocol.build_rtc_sync_packet())
                await self.enqueue_packet(WeekAquaProtocol.build_state_init_packet())

                # 활성화된 동적 스케줄이 있다면 현재 시각에 맞는 스펙트럼 즉시 갱신 전송
                if self.schedule_enabled and self.schedule_points:
                    target = self.calculate_interpolated_spectrum(datetime.now().time())
                    sched_pkt = WeekAquaProtocol.build_live_spectrum_packet(
                        target.r, target.g, target.b, target.w, target.uv, target.violet,
                        self.model_code, is_4ch_rgb_uv=self._is_4ch_rgb_uv()
                    )
                    self._last_sent_spectrum = sched_pkt
                    await self.enqueue_packet(sched_pkt, is_live_spectrum=True)

                return True

            except (BleakError, asyncio.TimeoutError, Exception) as err:
                _LOGGER.warning("Failed to connect to WeekAqua (%s): %s", self.mac, err)
                self.is_connected = False
                self._client = None
                self._write_char_uuid = None
                self._notify_char_uuid = None
                return False
            finally:
                self._is_connecting = False

    def _on_disconnected(self, client: Any) -> None:
        """Callback when BLE device disconnects."""
        self.is_connected = False
        self._client = None
        self._write_char_uuid = None
        self._notify_char_uuid = None
        if self._auto_disconnect_task:
            self._auto_disconnect_task.cancel()
        _LOGGER.info("WeekAqua (%s) disconnected", self.mac)
        self.async_set_updated_data(self._build_data())

    def _on_notify(self, sender: Any, data: bytearray) -> None:
        """Handle incoming notify packets from WeekAqua Smart Plug."""
        kwh = WeekAquaProtocol.parse_power_kwh(bytes(data))
        if kwh is not None:
            self.power_kwh = kwh
            self.async_set_updated_data(self._build_data())

    async def async_connect(self) -> bool:
        """Manually trigger connection to WeekAqua BLE device (Forces immediate connect)."""
        self._manual_disconnected = False
        connected = await self._ensure_connected(force=True)
        if connected:
            self._reset_inactivity_timer()
        return connected

    async def async_disconnect(self) -> None:
        """Explicitly disconnect BLE client to release device for other apps."""
        self._manual_disconnected = True
        if self._auto_disconnect_task:
            self._auto_disconnect_task.cancel()

        # 대기 중인 패킷 큐를 즉시 비워 워커가 재연결을 시도하지 않도록 방지
        while not self._write_queue.empty():
            try:
                self._write_queue.get_nowait()
                self._write_queue.task_done()
            except (asyncio.QueueEmpty, ValueError):
                break

        async with self._connect_lock:
            if self._client and self._client.is_connected:
                try:
                    await self._client.disconnect()
                except Exception:
                    pass
            self.is_connected = False
            self._client = None
            self._write_char_uuid = None
            self._notify_char_uuid = None
            _LOGGER.info("WeekAqua (%s) manually/automatically disconnected.", self.mac)
            self.async_set_updated_data(self._build_data())

    def _reset_inactivity_timer(self) -> None:
        """Reset the 60-second inactivity timer that automatically disconnects BLE."""
        if self._auto_disconnect_task and not self._auto_disconnect_task.done():
            self._auto_disconnect_task.cancel()
        self._auto_disconnect_task = asyncio.create_task(self._auto_disconnect_worker())

    async def _auto_disconnect_worker(self) -> None:
        """Worker task to automatically disconnect BLE after 60s of inactivity."""
        try:
            await asyncio.sleep(self._auto_disconnect_delay)
            _LOGGER.info(
                "Inactivity timeout (60s) reached for WeekAqua (%s). Releasing BLE session automatically.",
                self.mac
            )
            await self.async_disconnect()
        except asyncio.CancelledError:
            pass

    async def enqueue_packet(self, packet: bytes, is_live_spectrum: bool = False) -> None:
        """
        [핵심 개선 4] 큐 누적 및 패킷 홍수(Packet Flood) 방어 인큐잉.
        - 실시간 스펙트럼 패킷(FB F9)인 경우, 큐에 대기 중인 이전 스펙트럼 패킷을 버리고 항상 최신 1개만 유지.
        - 큐가 꽉 차있을 경우 오래된 패킷을 비워 버퍼 오버플로우 방지.
        """
        if is_live_spectrum:
            # 큐 안에 이미 대기 중인 패킷 중 실시간 스펙트럼(0xFB 0xF9) 패킷이 있으면 비워줌
            # (최신 스펙트럼 1개만 전송되도록 보장)
            temp_list = []
            while not self._write_queue.empty():
                try:
                    p = self._write_queue.get_nowait()
                    self._write_queue.task_done()
                    # 실시간 스펙트럼 패킷(FB F9)이 아닌 필수 제어 패킷(RTC 동기화 FF, 모드 설정 FD 등)만 보존
                    if not (len(p) == 8 and p[0] == 0xFB and p[1] == 0xF9):
                        temp_list.append(p)
                except (asyncio.QueueEmpty, ValueError):
                    break
            for p in temp_list:
                try:
                    self._write_queue.put_nowait(p)
                except asyncio.QueueFull:
                    break

        if self._write_queue.full():
            try:
                _ = self._write_queue.get_nowait()
                self._write_queue.task_done()
            except (asyncio.QueueEmpty, ValueError):
                pass

        try:
            self._write_queue.put_nowait(packet)
        except asyncio.QueueFull:
            pass

    async def _process_write_queue(self) -> None:
        """
        [핵심 개선 1] 락 격리 및 데드락이 없는 순차적 GATT 송신 워커.
        - _ensure_connected()를 락 내부에서 호출하지 않고 별도 실행하여 데드락을 원천 차단.
        - 패킷 송신 시에만 _write_lock을 점유하여 안전한 500ms 페이싱 전송 보장 (MCU 버퍼 오버런 방지).
        """
        while True:
            packet = await self._write_queue.get()
            try:
                # 1. 연결 확인 (연결 전용 로직은 _connect_lock이 담당하므로 워커 데드락 없음)
                connected = await self._ensure_connected()
                if connected and self._client and self._client.is_connected and self._write_char_uuid:
                    # 2. Zero-Latency RTC Sync: 0xFF 패킷은 송신 직전의 현재 시각으로 재생성
                    if len(packet) == 8 and packet[0] == 0xFF:
                        packet = WeekAquaProtocol.build_rtc_sync_packet(datetime.now())

                    # 3. GATT 쓰기 락 점유 후 안전한 순차 전송 (500ms 간격 유지)
                    async with self._write_lock:
                        await self._client.write_gatt_char(self._write_char_uuid, packet, response=False)
                        _LOGGER.info("TX -> %s (%s): %s", self.device_name, self.mac, packet.hex().upper())
                        await asyncio.sleep(0.5)
                        self._reset_inactivity_timer()
                else:
                    _LOGGER.debug(
                        "BLE TX skipped for %s (%s) - device offline or not ready. Packet: %s",
                        self.device_name, self.mac, packet.hex().upper()
                    )
            except Exception as ex:
                _LOGGER.error("BLE TX error on %s (%s): %s", self.device_name, self.mac, ex)
            finally:
                self._write_queue.task_done()

    # --- Unlimited Dynamic Schedule & Linear Ramp Engine ---

    def calculate_interpolated_spectrum(self, target_time: time | None = None) -> NormalizedSpectrum:
        """Calculate exact interpolated spectrum at given time using N waypoints."""
        if not self.schedule_points:
            return NormalizedSpectrum(0, 0, 0, 0, 0, 0)

        if target_time is None:
            target_time = datetime.now().time()

        now_sec = target_time.hour * 3600 + target_time.minute * 60 + target_time.second

        pts = self.schedule_points
        if len(pts) == 1:
            p = pts[0]
            return WeekAquaProtocol.normalize_spectrum_to_max_power(
                float(p.get("r", 0)), float(p.get("g", 0)), float(p.get("b", 0)),
                float(p.get("w", 0)), float(p.get("uv", 0)), float(p.get("v", 0)),
                self.model_code
            )

        start_h, start_m, start_s = parse_time_str(pts[0]["time"])
        end_h, end_m, end_s = parse_time_str(pts[-1]["time"])
        start_sec = start_h * 3600 + start_m * 60 + start_s
        end_sec = end_h * 3600 + end_m * 60 + end_s

        last_pt = pts[-1]
        end_spectrum = WeekAquaProtocol.normalize_spectrum_to_max_power(
            float(last_pt.get("r", 0)), float(last_pt.get("g", 0)), float(last_pt.get("b", 0)),
            float(last_pt.get("w", 0)), float(last_pt.get("uv", 0)), float(last_pt.get("v", 0)),
            self.model_code
        )

        # Check if in Night / Off hold period (from end_sec until start_sec)
        in_hold = False
        if end_sec <= start_sec:
            # Crosses midnight (e.g. 18:00 to 02:00). Hold interval: 02:00 <= now_sec < 18:00
            if end_sec <= now_sec < start_sec:
                in_hold = True
        else:
            # Same-day (e.g. 08:00 to 20:00). Hold interval: now_sec < 08:00 or now_sec >= 20:00
            if now_sec < start_sec or now_sec >= end_sec:
                in_hold = True

        if in_hold:
            return end_spectrum

        # Inside active schedule period -> Lerp along elapsed timeline from start_sec
        timeline: list[tuple[int, dict[str, float]]] = []
        for pt in pts:
            h, m, s = parse_time_str(pt["time"])
            sec = h * 3600 + m * 60 + s
            elapsed = (sec - start_sec) if sec >= start_sec else (86400 - start_sec + sec)
            timeline.append((elapsed, {
                "r": float(pt.get("r", 0)),
                "g": float(pt.get("g", 0)),
                "b": float(pt.get("b", 0)),
                "w": float(pt.get("w", 0)),
                "uv": float(pt.get("uv", 0)),
                "v": float(pt.get("v", 0)),
            }))

        timeline.sort(key=lambda x: x[0])
        elapsed_now = (now_sec - start_sec) if now_sec >= start_sec else (86400 - start_sec + now_sec)

        for i in range(len(timeline) - 1):
            if timeline[i][0] <= elapsed_now <= timeline[i + 1][0]:
                t1, spec1 = timeline[i]
                t2, spec2 = timeline[i + 1]
                ratio = (elapsed_now - t1) / (t2 - t1) if t2 > t1 else 0.0
                ratio = max(0.0, min(1.0, ratio))

                lerp_r = spec1["r"] + (spec2["r"] - spec1["r"]) * ratio
                lerp_g = spec1["g"] + (spec2["g"] - spec1["g"]) * ratio
                lerp_b = spec1["b"] + (spec2["b"] - spec1["b"]) * ratio
                lerp_w = spec1["w"] + (spec2["w"] - spec1["w"]) * ratio
                lerp_uv = spec1["uv"] + (spec2["uv"] - spec1["uv"]) * ratio
                lerp_v = spec1["v"] + (spec2["v"] - spec1["v"]) * ratio

                return WeekAquaProtocol.normalize_spectrum_to_max_power(
                    lerp_r, lerp_g, lerp_b, lerp_w, lerp_uv, lerp_v, self.model_code
                )

        return end_spectrum

    async def _async_update_data(self) -> dict[str, Any]:
        """
        [핵심 개선 4] 주기적 스케줄 계산 및 조건부 패킷 전송.
        - 기기가 오프라인일 때는 HA UI 상태만 실시간 계산하여 업데이트하고,
          BLE 큐에 불필요한 패킷을 밀어 넣지 않아 패킷 홍수를 방지합니다.
        """
        now = datetime.now()

        # 1. 일일 자동 RTC 동기화 (하루 1회 자정에 실행)
        if self._last_rtc_sync_date != now.date():
            self._last_rtc_sync_date = now.date()
            if self.is_connected:
                _LOGGER.info(
                    "Performing daily automatic RTC clock sync for WeekAqua (%s) at %s",
                    self.mac,
                    now.strftime("%Y-%m-%d %H:%M:%S")
                )
                await self.enqueue_packet(WeekAquaProtocol.build_rtc_sync_packet(now))

        # 2. 동적 스케줄 실시간 보간 계산
        if self.schedule_enabled and self.schedule_points:
            target = self.calculate_interpolated_spectrum(now.time())
            self.current_r = target.r
            self.current_g = target.g
            self.current_b = target.b
            self.current_w = target.w
            self.current_uv = target.uv
            self.current_v = target.violet

            packet = WeekAquaProtocol.build_live_spectrum_packet(
                self.current_r, self.current_g, self.current_b, self.current_w,
                self.current_uv, self.current_v, self.model_code,
                is_4ch_rgb_uv=self._is_4ch_rgb_uv()
            )

            # 사용자가 수동으로 연결을 해제하지 않았고 스펙트럼이 실제로 변경되었을 때만 큐에 전송
            if not self._manual_disconnected:
                if packet != self._last_sent_spectrum and self.is_connected:
                    self._last_sent_spectrum = packet
                    await self.enqueue_packet(packet, is_live_spectrum=True)

        self.total_power_pct = WeekAquaProtocol.calculate_total_power_percent(
            self.current_r, self.current_g, self.current_b, self.current_w,
            self.current_uv, self.current_v, self.model_code
        )
        self.async_set_updated_data(self._build_data())

    async def async_set_schedule_enabled(self, enabled: bool) -> None:
        """Enable or disable dynamic unlimited schedule."""
        self.schedule_enabled = enabled
        _LOGGER.info("Dynamic schedule %s for %s", "ENABLED" if enabled else "DISABLED", self.mac)
        if enabled and self.schedule_points:
            target = self.calculate_interpolated_spectrum(datetime.now().time())
            self.current_r = target.r
            self.current_g = target.g
            self.current_b = target.b
            self.current_w = target.w
            self.current_uv = target.uv
            self.current_v = target.violet
            packet = WeekAquaProtocol.build_live_spectrum_packet(
                self.current_r, self.current_g, self.current_b, self.current_w,
                self.current_uv, self.current_v, self.model_code,
                is_4ch_rgb_uv=self._is_4ch_rgb_uv()
            )
            self._last_sent_spectrum = packet
            if not self._manual_disconnected:
                await self.enqueue_packet(packet, is_live_spectrum=True)
        self.total_power_pct = WeekAquaProtocol.calculate_total_power_percent(
            self.current_r, self.current_g, self.current_b, self.current_w,
            self.current_uv, self.current_v, self.model_code
        )
        self.async_set_updated_data(self._build_data())

    def _build_data(self) -> dict[str, Any]:
        """Construct dictionary of current state for HA entities."""
        return {
            "connected": self.is_connected,
            "r": self.current_r,
            "g": self.current_g,
            "b": self.current_b,
            "w": self.current_w,
            "uv": self.current_uv,
            "v": self.current_v,
            "fan": self.current_fan,
            "power_pct": self.total_power_pct,
            "power_kwh": self.power_kwh,
            "schedule_enabled": self.schedule_enabled,
            "schedule_points": self.schedule_points,
            "schedule_meta": self.schedule_meta,
        }

    # --- Public Control Methods (Called by Entities & Services) ---

    async def async_set_spectrum(
        self,
        r: float,
        g: float,
        b: float,
        w: float,
        uv: float = 0.0,
        violet: float = 0.0,
        disable_schedule: bool = True
    ) -> None:
        """Set manual spectrum immediately."""
        if disable_schedule:
            self.schedule_enabled = False

        norm = WeekAquaProtocol.normalize_spectrum_to_max_power(r, g, b, w, uv, violet, self.model_code)
        self.current_r = norm.r
        self.current_g = norm.g
        self.current_b = norm.b
        self.current_w = norm.w
        self.current_uv = norm.uv
        self.current_v = norm.violet

        packet = WeekAquaProtocol.build_live_spectrum_packet(
            self.current_r, self.current_g, self.current_b, self.current_w,
            self.current_uv, self.current_v, self.model_code,
            is_4ch_rgb_uv=self._is_4ch_rgb_uv()
        )
        self._last_sent_spectrum = packet
        await self.enqueue_packet(packet, is_live_spectrum=True)
        self.async_set_updated_data(self._build_data())

    async def async_set_fan_speed(self, fan_pct: float) -> None:
        """Set fan speed (0.0 ~ 100.0%)."""
        self.current_fan = max(0.0, min(100.0, float(fan_pct)))
        packet = WeekAquaProtocol.build_fan_speed_packet(self.current_fan)
        await self.enqueue_packet(packet)
        self.async_set_updated_data(self._build_data())

    async def async_set_schedule(
        self,
        points: list[dict[str, Any]],
        meta: dict[str, Any] | None = None
    ) -> None:
        """Update unlimited schedule waypoints and metadata, then persist and re-evaluate immediately."""
        self.schedule_points = points
        if meta:
            self.schedule_meta = {**self.schedule_meta, **{k: v for k, v in meta.items() if v is not None}}
        self.schedule_enabled = True

        # Persist to ConfigEntry storage across HA restarts
        if self._entry:
            try:
                new_data = {
                    **self._entry.data,
                    CONF_SCHEDULE: points,
                    "schedule_meta": self.schedule_meta,
                }
                self.hass.config_entries.async_update_entry(self._entry, data=new_data)
            except Exception as err:
                _LOGGER.debug("Failed to persist schedule to config entry: %s", err)

        self.async_set_updated_data(self._build_data())
        await self.async_refresh()

    async def async_set_hardware_timer(
        self,
        start_time_str: str,
        end_time_str: str,
        r: float,
        g: float,
        b: float,
        w: float,
        uv: float = 0.0,
        violet: float = 0.0,
        ramp_idx: int = 2
    ) -> None:
        """Send hardware schedule timer to WeekAqua MCU.
        If the schedule crosses midnight (e.g. 18:00 to 02:00),
        it automatically splits into two consecutive hardware schedule slots:
        1. Day 1: start_time ~ 24:00 (0x24 0x00)
        2. Day 2: 00:00 ~ end_time (0x00 0x00)
        Transmits Mode 2 (Advanced Ramp Mode) and RTC sync for seamless, gapless continuous lighting.
        """
        self.schedule_enabled = False

        start_h, start_m, _ = parse_time_str(start_time_str)
        end_h, end_m, _ = parse_time_str(end_time_str)

        intervals = WeekAquaProtocol.split_cross_midnight_timer(start_h, start_m, end_h, end_m)

        # 0. Prepend RTC clock sync packet
        await self.enqueue_packet(WeekAquaProtocol.build_rtc_sync_packet(datetime.now()))

        if len(intervals) == 2:
            # Crosses midnight: send two schedule slots
            # Slot 1: Day 1 (start_h:start_m -> 24:00)
            int1 = intervals[0]
            t_pkt1 = WeekAquaProtocol.build_ramp_time_packet(1, int1[0], int1[1], int1[2], int1[3], enabled=True)
            s_pkt1 = WeekAquaProtocol.build_ramp_spectrum_packet(
                1, r, g, b, w, uv, violet, self.model_code, is_4ch_rgb_uv=self._is_4ch_rgb_uv()
            )
            await self.enqueue_packet(t_pkt1)
            await self.enqueue_packet(s_pkt1)

            # Slot 2: Day 2 (00:00 -> end_h:end_m)
            int2 = intervals[1]
            t_pkt2 = WeekAquaProtocol.build_ramp_time_packet(2, int2[0], int2[1], int2[2], int2[3], enabled=True)
            s_pkt2 = WeekAquaProtocol.build_ramp_spectrum_packet(
                2, r, g, b, w, uv, violet, self.model_code, is_4ch_rgb_uv=self._is_4ch_rgb_uv()
            )
            await self.enqueue_packet(t_pkt2)
            await self.enqueue_packet(s_pkt2)

            # Activate Mode 2 (Advanced Custom Ramp Schedule Mode)
            await self.enqueue_packet(WeekAquaProtocol.build_mode_packet(2))
            _LOGGER.info(
                "Sent 2-slot cross-midnight hardware schedule for WeekAqua (%s): %02d:%02d~24:00 & 00:00~%02d:%02d",
                self.mac, int1[0], int1[1], int2[2], int2[3]
            )
        else:
            # Single same-day schedule
            int1 = intervals[0]
            t_pkt1 = WeekAquaProtocol.build_ramp_time_packet(1, int1[0], int1[1], int1[2], int1[3], enabled=True)
            s_pkt1 = WeekAquaProtocol.build_ramp_spectrum_packet(
                1, r, g, b, w, uv, violet, self.model_code, is_4ch_rgb_uv=self._is_4ch_rgb_uv()
            )
            await self.enqueue_packet(t_pkt1)
            await self.enqueue_packet(s_pkt1)

            # Activate Mode 2
            await self.enqueue_packet(WeekAquaProtocol.build_mode_packet(2))
            _LOGGER.info(
                "Sent single-slot hardware schedule for WeekAqua (%s): %02d:%02d~%02d:%02d",
                self.mac, int1[0], int1[1], int1[2], int1[3]
            )

        self.async_set_updated_data(self._build_data())

    async def async_set_schedule_enabled(self, enabled: bool) -> None:
        """Toggle dynamic schedule on or off."""
        self.schedule_enabled = enabled
        if enabled:
            await self.async_refresh()
        else:
            self.async_set_updated_data(self._build_data())
