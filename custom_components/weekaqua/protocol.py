"""WeekAqua BLE Protocol Implementation in Python.

Reverse-engineered from WeekAqua Android APK and verified with WeekAquaWPF.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, time
import math


@dataclass
class NormalizedSpectrum:
    r: float
    g: float
    b: float
    w: float
    uv: float
    violet: float


class WeekAquaProtocol:
    """Protocol packet builder and parser for WeekAqua BLE devices."""

    @staticmethod
    def percent_to_byte(percent: float) -> int:
        """Convert 0.0~100.0% to WeekAqua linear byte 0x00~0xEB (235 max)."""
        clamped = max(0.0, min(100.0, float(percent)))
        val = int(round(clamped * 2.35))
        return max(0, min(235, val))

    @staticmethod
    def byte_to_percent(b: int) -> float:
        """Convert WeekAqua byte 0x00~0xEB to percentage 0.0~100.0%."""
        val = max(0, min(235, int(b)))
        return round(val / 2.35, 1)

    @staticmethod
    def decimal_to_bcd(val: int) -> int:
        """Convert integer (0-99) to BCD encoded byte."""
        clamped = max(0, min(99, int(val)))
        high = clamped // 10
        low = clamped % 10
        return (high << 4) | low

    @staticmethod
    def bcd_to_decimal(bcd: int) -> int:
        """Convert BCD byte to integer decimal."""
        high = (bcd >> 4) & 0x0F
        low = bcd & 0x0F
        return high * 10 + low

    @staticmethod
    def calculate_total_power_percent(
        red: float,
        green: float,
        blue: float,
        white: float,
        uv: float = 0.0,
        violet: float = 0.0,
        model_code: str = ""
    ) -> float:
        """Calculate total wattage load percentage according to official APK formulas."""
        r = max(0.0, min(100.0, red))
        g = max(0.0, min(100.0, green))
        b = max(0.0, min(100.0, blue))
        w = max(0.0, min(100.0, white))
        u = max(0.0, min(100.0, uv))
        v = max(0.0, min(100.0, violet))

        if model_code == "5748":  # 5-Channel Mode 5
            total = (r * 0.41) + (g * 0.42) + (b * 0.49) + (w * 0.08) + (u * 0.08)
        elif model_code == "5749":  # 6-Channel Mode 6
            total = (r * 0.41) + (g * 0.42) + (b * 0.49) + (w * 0.08) + (u * 0.08) + (v * 0.08)
        elif model_code in ("5750", "5751", "5752"):  # 7+ Channel Advanced
            total = ((r * 0.29) + (g * 0.69) + (b * 0.73) + (w * 0.10) + (u * 0.40) + (v * 0.40)) / 1.06
        else:  # Standard 4-Channel (5746/5747)
            total = (r * 0.39) + (g * 0.41) + (b * 0.53) + (w * 0.11)

        rounded = round(total, 1)
        return 100.0 if 100.0 < rounded <= 100.15 else rounded

    @classmethod
    def normalize_spectrum_to_max_power(
        cls,
        red: float,
        green: float,
        blue: float,
        white: float,
        uv: float = 0.0,
        violet: float = 0.0,
        model_code: str = ""
    ) -> NormalizedSpectrum:
        """Proportionally scale down all channels if total power exceeds 100%."""
        total_power = cls.calculate_total_power_percent(red, green, blue, white, uv, violet, model_code)
        if total_power <= 100.0 or total_power <= 0.0:
            return NormalizedSpectrum(
                r=round(max(0.0, red), 1),
                g=round(max(0.0, green), 1),
                b=round(max(0.0, blue), 1),
                w=round(max(0.0, white), 1),
                uv=round(max(0.0, uv), 1),
                violet=round(max(0.0, violet), 1),
            )

        scale_factor = 99.8 / total_power
        r = round(red * scale_factor, 1)
        g = round(green * scale_factor, 1)
        b = round(blue * scale_factor, 1)
        w = round(white * scale_factor, 1)
        u = round(uv * scale_factor, 1)
        v = round(violet * scale_factor, 1)

        safety_count = 0
        while cls.calculate_total_power_percent(r, g, b, w, u, v, model_code) > 100.0 and safety_count < 10:
            safety_count += 1
            if b >= r and b >= g and b >= w and b >= u and b >= v and b > 0:
                b = round(b - 0.1, 1)
            elif g >= r and g >= w and g >= u and g >= v and g > 0:
                g = round(g - 0.1, 1)
            elif r >= w and r >= u and r >= v and r > 0:
                r = round(r - 0.1, 1)
            elif w >= u and w >= v and w > 0:
                w = round(w - 0.1, 1)
            elif u >= v and u > 0:
                u = round(u - 0.1, 1)
            elif v > 0:
                v = round(v - 0.1, 1)

        return NormalizedSpectrum(
            r=max(0.0, r),
            g=max(0.0, g),
            b=max(0.0, b),
            w=max(0.0, w),
            uv=max(0.0, u),
            violet=max(0.0, v),
        )

    @classmethod
    def build_live_spectrum_packet(
        cls,
        red_pct: float,
        green_pct: float,
        blue_pct: float,
        white_pct: float,
        uv_pct: float = 0.0,
        violet_pct: float = 0.0,
        model_code: str = "",
        is_4ch_rgb_uv: bool = False
    ) -> bytes:
        """Build live manual spectrum packet matching official APK / WPF specification.
        For 4-Channel RGB/UV models (M800 Pro, M600, S-Series, T90, 5746):
          Channel 4 is mapped to Byte 5 (UV if uv_pct > 0 else white_pct).
          Total 8 bytes: [0xFB, 0xF9, R, G, B, CH4, 0x55, 0x55].
        For 5-Channel (5748):
          Total 9 bytes: [0xFB, 0xF9, R, G, B, W, UV, 0x55, 0x55].
        For 6-Channel (5749/5751/5752):
          Total 10 bytes: [0xFB, 0xF9, R, G, B, W, UV, V, 0x55, 0x55].
        For standard 4-Channel RGBW (5745):
          Total 8 bytes: [0xFB, 0xF9, R, G, B, W, 0x55, 0x55].
        """
        norm = cls.normalize_spectrum_to_max_power(red_pct, green_pct, blue_pct, white_pct, uv_pct, violet_pct, model_code)
        r = cls.percent_to_byte(norm.r)
        g = cls.percent_to_byte(norm.g)
        b = cls.percent_to_byte(norm.b)
        w = cls.percent_to_byte(norm.w)
        uv = cls.percent_to_byte(norm.uv)
        v = cls.percent_to_byte(norm.violet)

        # 4-Channel RGB/UV (e.g. M800 Pro, M-Series, S-Series, T90, Model 5746)
        if is_4ch_rgb_uv or model_code == "5746":
            ch4 = uv if uv > 0 else w
            return bytes([0xFB, 0xF9, r, g, b, ch4, 0x55, 0x55])

        if v > 0 or model_code in ("5749", "5750", "5751", "5752"):
            return bytes([0xFB, 0xF9, r, g, b, w, uv, v, 0x55, 0x55])

        if uv > 0 or model_code == "5748":
            return bytes([0xFB, 0xF9, r, g, b, w, uv, 0x55, 0x55])

        return bytes([0xFB, 0xF9, r, g, b, w, 0x55, 0x55])

    @classmethod
    def build_fan_speed_packet(cls, fan_pct: float) -> bytes:
        """Build 8-byte cooling fan speed packet (0xFC fan 0x55 0x55 0x55 0x55 0x55 0x55)."""
        f = cls.percent_to_byte(fan_pct)
        return bytes([0xFC, f, 0x55, 0x55, 0x55, 0x55, 0x55, 0x55])

    @classmethod
    def build_rtc_sync_packet(cls, dt: datetime | None = None) -> bytes:
        """Build 8-byte real-time clock synchronization packet with BCD encoding."""
        if dt is None:
            dt = datetime.now()
        h_bcd = cls.decimal_to_bcd(dt.hour)
        m_bcd = cls.decimal_to_bcd(dt.minute)
        s_bcd = cls.decimal_to_bcd(dt.second)
        return bytes([0xFF, h_bcd, m_bcd, s_bcd, 0x55, 0x55, 0x55, 0x55])

    @classmethod
    def build_state_init_packet(cls) -> bytes:
        """Build 8-byte state initialization query packet (0xF0 0x55 ...)."""
        return bytes([0xF0, 0x55, 0x55, 0x55, 0x55, 0x55, 0x55, 0x55])

    @classmethod
    def build_mode_packet(cls, mode_id: int) -> bytes:
        """Build mode activation packet (0xFD 0xF1 ~ 0xF3). Mode 1: Sunrise/Sunset, Mode 2: Ramp, Mode 3: Manual."""
        sub = 0xF1 if mode_id == 1 else (0xF2 if mode_id == 2 else 0xF3)
        return bytes([0xFD, sub, 0x55, 0x55, 0x55, 0x55, 0x55, 0x55])

    @classmethod
    def build_ramp_time_packet(
        cls,
        slot_id: int,
        start_h: int,
        start_m: int,
        end_h: int,
        end_m: int,
        enabled: bool = True
    ) -> bytes:
        """Build 8-byte Ramp schedule slot time packet (0xFE 0xF[slot] BCD(StartH) BCD(StartM) BCD(EndH) BCD(EndM) 0x55 0x55).
        Slot ID: 1 to 12.
        Supports 24:00 (end_h=24 -> BCD 0x24) for gapless midnight transition.
        """
        if not 1 <= slot_id <= 12:
            raise ValueError(f"Slot ID must be between 1 and 12, got {slot_id}")
        second_header = 0xF0 | (slot_id & 0x0F)
        if not enabled:
            return bytes([0xFE, second_header, 0x00, 0x00, 0x00, 0x00, 0x55, 0x55])
        return bytes([
            0xFE,
            second_header,
            cls.decimal_to_bcd(start_h),
            cls.decimal_to_bcd(start_m),
            cls.decimal_to_bcd(end_h),
            cls.decimal_to_bcd(end_m),
            0x55,
            0x55
        ])

    @classmethod
    def build_ramp_spectrum_packet(
        cls,
        slot_id: int,
        red_pct: float,
        green_pct: float,
        blue_pct: float,
        white_pct: float,
        uv_pct: float = 0.0,
        violet_pct: float = 0.0,
        model_code: str = "",
        is_4ch_rgb_uv: bool = False
    ) -> bytes:
        """Build 8~10 byte Ramp schedule slot spectrum packet (0xFB 0xF[slot] R G B W UV V 0x55 0x55)."""
        if not 1 <= slot_id <= 12:
            raise ValueError(f"Slot ID must be between 1 and 12, got {slot_id}")
        second_header = 0xF0 | (slot_id & 0x0F)
        norm = cls.normalize_spectrum_to_max_power(red_pct, green_pct, blue_pct, white_pct, uv_pct, violet_pct, model_code)
        r = cls.percent_to_byte(norm.r)
        g = cls.percent_to_byte(norm.g)
        b = cls.percent_to_byte(norm.b)
        w = cls.percent_to_byte(norm.w)
        uv = cls.percent_to_byte(norm.uv)
        v = cls.percent_to_byte(norm.violet)

        if is_4ch_rgb_uv or model_code == "5746":
            ch4 = uv if uv > 0 else w
            return bytes([0xFB, second_header, r, g, b, ch4, 0x55, 0x55])

        if v > 0 or model_code in ("5749", "5750", "5751", "5752"):
            return bytes([0xFB, second_header, r, g, b, w, uv, v, 0x55, 0x55])

        if uv > 0 or model_code == "5748":
            return bytes([0xFB, second_header, r, g, b, w, uv, 0x55, 0x55])

        return bytes([0xFB, second_header, r, g, b, w, 0x55, 0x55])

    @classmethod
    def build_sunrise_sunset_packet(
        cls,
        start_h: int,
        start_m: int,
        end_h: int,
        end_m: int,
        ramp_idx: int = 2,
        enabled: bool = True
    ) -> bytes:
        """Build dedicated Sunrise/Sunset timer packet (0xFE 0xF9 BCD(StartH) BCD(StartM) BCD(EndH) BCD(EndM) 0x01 RampIdx)."""
        return bytes([
            0xFE,
            0xF9,
            cls.decimal_to_bcd(start_h),
            cls.decimal_to_bcd(start_m),
            cls.decimal_to_bcd(end_h),
            cls.decimal_to_bcd(end_m),
            0x01 if enabled else 0x00,
            max(0, min(5, int(ramp_idx)))
        ])

    @staticmethod
    def split_cross_midnight_timer(
        start_h: int,
        start_m: int,
        end_h: int,
        end_m: int
    ) -> list[tuple[int, int, int, int]]:
        """Split a schedule/timer that crosses midnight into two gapless 24-hour schedule intervals:
        1. Day 1: start_time ~ 24:00 (0x24 0x00)
        2. Day 2: 00:00 ~ end_time (0x00 0x00)
        If the timer does not cross midnight, returns a single interval [(start_h, start_m, end_h, end_m)].
        """
        # If identical times -> full 24h
        if start_h == end_h and start_m == end_m:
            return [(start_h, start_m, 24, 0)]

        # If crossing midnight (e.g. 18:00 to 02:00)
        if start_h > end_h or (start_h == end_h and start_m > end_m):
            return [
                (start_h, start_m, 24, 0),  # Slot 1: e.g. 18:00 -> 24:00
                (0, 0, end_h, end_m)        # Slot 2: e.g. 00:00 -> 02:00
            ]

        # If ending at midnight exactly (e.g. 16:00 to 00:00)
        if end_h == 0 and end_m == 0 and (start_h > 0 or start_m > 0):
            return [(start_h, start_m, 24, 0)]

        # Standard same-day schedule (e.g. 08:00 to 20:00)
        return [(start_h, start_m, end_h, end_m)]

    @staticmethod
    def parse_power_kwh(data: bytes) -> float | None:
        """Parse accumulated energy (kWh) from Smart Plug GATT Notify characteristic."""
        if len(data) >= 8 and data[0] == 0xFC and data[1] == 0xFD:
            raw_val = (data[2] << 24) | (data[3] << 16) | (data[4] << 8) | data[5]
            kwh = raw_val * 4.656612873077393e-8
            return round(kwh, 4)
        return None
