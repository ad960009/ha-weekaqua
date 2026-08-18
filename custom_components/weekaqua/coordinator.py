"""DataUpdateCoordinator and Schedule Engine for WeekAqua."""

from __future__ import annotations
import asyncio
from datetime import datetime, date, time, timedelta
import logging
from typing import Any

from bleak import BleakClient
from bleak.exc import BleakError
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    establish_connection,
)

from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant, callback
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


class WeekAquaCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator managing WeekAqua BLE communication and the Unlimited Dynamic Schedule Engine."""

    def __init__(self, hass: HomeAssistant, entry_data: dict[str, Any]) -> None:
        """Initialize the WeekAqua coordinator."""
        self.mac: str = entry_data[CONF_MAC]
        self.device_name: str = entry_data.get(CONF_NAME, "WeekAqua")
        self.model_code: str = entry_data.get(CONF_MODEL_CODE, "")
        self.keep_moonlight: bool = entry_data.get(CONF_KEEP_MOONLIGHT, True)
        self.schedule_interval: int = entry_data.get(CONF_SCHEDULE_INTERVAL, DEFAULT_SCHEDULE_INTERVAL)

        # Dynamic Unlimited Schedule Waypoints: list of dicts {"time": "08:00", "r": 0, "g": 0, "b": 0, "w": 0, "uv": 0, "v": 0}
        self.schedule_points: list[dict[str, Any]] = entry_data.get(CONF_SCHEDULE, self._get_default_schedule())
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

        # Bleak Client & Lock
        self._client: BleakClientWithServiceCache | BleakClient | None = None
        self._write_char_uuid: str | None = None
        self._notify_char_uuid: str | None = None
        self._lock = asyncio.Lock()
        self._write_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._queue_task: asyncio.Task | None = None
        self._auto_disconnect_task: asyncio.Task | None = None
        self._auto_disconnect_delay: float = 60.0  # Disconnect after 60s of inactivity
        self._schedule_unsub: Any = None
        self._last_sent_spectrum: bytes | None = None
        self._last_rtc_sync_date: date | None = None

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{self.mac}",
            update_interval=timedelta(seconds=self.schedule_interval),
        )

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

    async def _ensure_connected(self) -> bool:
        """Ensure Bleak connection using Home Assistant Bluetooth backend / BLE Proxy."""
        if self._client and self._client.is_connected and self._write_char_uuid:
            return True

        ble_device = bluetooth.async_ble_device_from_address(self.hass, self.mac, connectable=True)
        if not ble_device:
            # Fallback to non-connectable scanner cache
            ble_device = bluetooth.async_ble_device_from_address(self.hass, self.mac, connectable=False)

        if not ble_device:
            _LOGGER.warning(
                "WeekAqua (%s) was not found in Home Assistant Bluetooth scanner cache. "
                "Please verify the light is powered on, within Bluetooth range, and not connected to phone app.",
                self.mac
            )
            return False

        # Auto-update device_name and model_code from live BLE scan data if currently generic
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

        try:
            _LOGGER.info("Connecting to WeekAqua BLE %s (%s)...", self.device_name, self.mac)
            self._client = await establish_connection(
                BleakClientWithServiceCache,
                ble_device,
                self.device_name,
                self._on_disconnected,
                max_attempts=3,
                use_services_cache=True,
            )
            self.is_connected = True
            _LOGGER.info("Connected to WeekAqua BLE %s (%s) successfully!", self.device_name, self.mac)

            # Discover and resolve Write and Notify characteristics
            self._write_char_uuid = None
            self._notify_char_uuid = None

            # 1. Search known UUID lists in discovered services
            for s in self._client.services:
                for c in s.characteristics:
                    c_uuid_lower = c.uuid.lower()
                    for target_write in WRITE_CHAR_UUIDS:
                        if target_write.lower() == c_uuid_lower:
                            self._write_char_uuid = c.uuid
                            break
                    for target_notify in NOTIFY_CHAR_UUIDS:
                        if target_notify.lower() == c_uuid_lower:
                            self._notify_char_uuid = c.uuid
                            break

            # 2. Fallback to any characteristic with write property if not in known lists
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

            # Subscribe to GATT Notify for Smart Plug Power Meter
            if self._notify_char_uuid:
                try:
                    await self._client.start_notify(self._notify_char_uuid, self._on_notify)
                    _LOGGER.info("Subscribed to GATT Notify: %s on %s", self._notify_char_uuid, self.mac)
                except Exception as notify_err:
                    _LOGGER.debug("Notify subscription on %s skipped: %s", self.mac, notify_err)

            # Sync RTC time and query initial state
            await self.enqueue_packet(WeekAquaProtocol.build_rtc_sync_packet())
            await self.enqueue_packet(WeekAquaProtocol.build_state_init_packet())
            return True
        except (BleakError, asyncio.TimeoutError, Exception) as err:
            _LOGGER.warning("Failed to connect to WeekAqua (%s): %s", self.mac, err)
            self.is_connected = False
            self._client = None
            self._write_char_uuid = None
            self._notify_char_uuid = None
            return False

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
        """Manually trigger connection to WeekAqua BLE device."""
        async with self._lock:
            connected = await self._ensure_connected()
            if connected:
                self._reset_inactivity_timer()
            return connected

    async def async_disconnect(self) -> None:
        """Explicitly disconnect BLE client to release device for other apps."""
        if self._auto_disconnect_task:
            self._auto_disconnect_task.cancel()
        async with self._lock:
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

    async def enqueue_packet(self, packet: bytes) -> None:
        """Enqueue an 8-byte command packet to be transmitted."""
        await self._write_queue.put(packet)

    async def _process_write_queue(self) -> None:
        """Sequential writer with 500ms pacing to prevent packet collision."""
        while True:
            packet = await self._write_queue.get()
            try:
                async with self._lock:
                    connected = await self._ensure_connected()
                    if connected and self._client and self._client.is_connected and self._write_char_uuid:
                        # Zero-Latency RTC Sync: If this is an RTC sync packet (starts with 0xFF),
                        # dynamically regenerate it with datetime.now() right before transmission
                        # to eliminate BLE connection handshaking and queue latency.
                        if len(packet) == 8 and packet[0] == 0xFF:
                            packet = WeekAquaProtocol.build_rtc_sync_packet(datetime.now())

                        await self._client.write_gatt_char(self._write_char_uuid, packet, response=False)
                        _LOGGER.info("TX -> %s (%s): %s", self.device_name, self.mac, packet.hex().upper())
                        await asyncio.sleep(0.5)
                        self._reset_inactivity_timer()
                    else:
                        _LOGGER.warning("BLE TX skipped for %s (%s) - device offline or no write char. Packet: %s", self.device_name, self.mac, packet.hex().upper())
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

        # Convert waypoints to (seconds, spectrum)
        points: list[tuple[int, dict[str, float]]] = []
        for pt in self.schedule_points:
            h, m, s = parse_time_str(pt["time"])
            sec = min(86400, h * 3600 + m * 60 + s)
            points.append((sec, {
                "r": float(pt.get("r", 0)),
                "g": float(pt.get("g", 0)),
                "b": float(pt.get("b", 0)),
                "w": float(pt.get("w", 0)),
                "uv": float(pt.get("uv", 0)),
                "v": float(pt.get("v", 0)),
            }))

        points.sort(key=lambda x: x[0])

        if len(points) == 1:
            p = points[0][1]
            return WeekAquaProtocol.normalize_spectrum_to_max_power(p["r"], p["g"], p["b"], p["w"], p["uv"], p["v"], self.model_code)

        # Find surrounding waypoints (p1 -> p2)
        p1 = points[-1]
        p2 = points[0]

        for i in range(len(points) - 1):
            if points[i][0] <= now_sec < points[i + 1][0]:
                p1 = points[i]
                p2 = points[i + 1]
                break

        # Calculate progress ratio t in [0.0, 1.0]
        t1, spec1 = p1
        t2, spec2 = p2

        if t2 > t1:
            progress = (now_sec - t1) / (t2 - t1)
        else:
            # Wrap around midnight (e.g. 23:00 to 08:00)
            span = (86400 - t1) + t2
            elapsed = (now_sec - t1) if now_sec >= t1 else (86400 - t1 + now_sec)
            progress = elapsed / span if span > 0 else 0.0

        progress = max(0.0, min(1.0, progress))

        # Linear Interpolation (Lerp)
        lerp_r = spec1["r"] + (spec2["r"] - spec1["r"]) * progress
        lerp_g = spec1["g"] + (spec2["g"] - spec1["g"]) * progress
        lerp_b = spec1["b"] + (spec2["b"] - spec1["b"]) * progress
        lerp_w = spec1["w"] + (spec2["w"] - spec1["w"]) * progress
        lerp_uv = spec1["uv"] + (spec2["uv"] - spec1["uv"]) * progress
        lerp_v = spec1["v"] + (spec2["v"] - spec1["v"]) * progress

        return WeekAquaProtocol.normalize_spectrum_to_max_power(lerp_r, lerp_g, lerp_b, lerp_w, lerp_uv, lerp_v, self.model_code)

    async def _async_update_data(self) -> dict[str, Any]:
        """Periodic schedule evaluator and BLE synchronization tick."""
        now = datetime.now()

        # Daily Automatic RTC Synchronization (Runs once per day at midnight / date change)
        if self._last_rtc_sync_date != now.date():
            self._last_rtc_sync_date = now.date()
            _LOGGER.info(
                "Performing daily automatic RTC clock sync for WeekAqua (%s) at %s",
                self.mac,
                now.strftime("%Y-%m-%d %H:%M:%S")
            )
            await self.enqueue_packet(WeekAquaProtocol.build_rtc_sync_packet(now))

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

            # Send only if spectrum changed significantly or on reconnection
            if packet != self._last_sent_spectrum or not self.is_connected:
                self._last_sent_spectrum = packet
                await self.enqueue_packet(packet)

        self.total_power_pct = WeekAquaProtocol.calculate_total_power_percent(
            self.current_r, self.current_g, self.current_b, self.current_w,
            self.current_uv, self.current_v, self.model_code
        )

        return self._build_data()

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
            "connected": self.is_connected,
            "power_pct": self.total_power_pct,
            "power_kwh": self.power_kwh,
            "schedule_enabled": self.schedule_enabled,
            "schedule_points": self.schedule_points,
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
        await self.enqueue_packet(packet)
        self.async_set_updated_data(self._build_data())

    async def async_set_fan_speed(self, fan_pct: float) -> None:
        """Set fan speed (0.0 ~ 100.0%)."""
        self.current_fan = max(0.0, min(100.0, float(fan_pct)))
        packet = WeekAquaProtocol.build_fan_speed_packet(self.current_fan)
        await self.enqueue_packet(packet)
        self.async_set_updated_data(self._build_data())

    async def async_set_schedule(self, points: list[dict[str, Any]]) -> None:
        """Update unlimited schedule waypoints and re-evaluate immediately."""
        self.schedule_points = points
        self.schedule_enabled = True
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
