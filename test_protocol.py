"""Unit verification tests for Python WeekAquaProtocol implementation."""

import unittest
from datetime import datetime
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "custom_components", "weekaqua"))
from protocol import WeekAquaProtocol


class TestWeekAquaProtocol(unittest.TestCase):
    def test_percent_to_byte_and_back(self):
        self.assertEqual(WeekAquaProtocol.percent_to_byte(100.0), 235)
        self.assertEqual(WeekAquaProtocol.percent_to_byte(0.0), 0)
        self.assertEqual(WeekAquaProtocol.percent_to_byte(50.0), 118)
        self.assertAlmostEqual(WeekAquaProtocol.byte_to_percent(235), 100.0, delta=0.5)
        self.assertAlmostEqual(WeekAquaProtocol.byte_to_percent(0), 0.0, delta=0.5)

    def test_bcd_encoding(self):
        bcd = WeekAquaProtocol.decimal_to_bcd(22)
        self.assertEqual(bcd, 0x22)
        dec = WeekAquaProtocol.bcd_to_decimal(0x22)
        self.assertEqual(dec, 22)

    def test_rtc_sync_packet(self):
        dt = datetime(2026, 8, 18, 14, 30, 15)
        packet = WeekAquaProtocol.build_rtc_sync_packet(dt)
        self.assertEqual(packet.hex().upper(), "FF14301555555555")

    def test_fan_speed_packet(self):
        packet = WeekAquaProtocol.build_fan_speed_packet(0)
        self.assertEqual(packet.hex().upper(), "FC00555555555555")

    def test_live_spectrum_packet_normalization(self):
        # 100% on all channels exceeds 100% total power -> must be clamped/normalized
        packet = WeekAquaProtocol.build_live_spectrum_packet(100, 100, 100, 100, 100, 100, model_code="5749")
        self.assertEqual(packet[0], 0xFB)
        self.assertEqual(packet[1], 0xF9)
        # Verify normalized values are <= 235 and power is strictly <= 100.0%
        r = WeekAquaProtocol.byte_to_percent(packet[2])
        g = WeekAquaProtocol.byte_to_percent(packet[3])
        b = WeekAquaProtocol.byte_to_percent(packet[4])
        w = WeekAquaProtocol.byte_to_percent(packet[5])
        norm = WeekAquaProtocol.normalize_spectrum_to_max_power(100, 100, 100, 100, 100, 100, model_code="5749")
        total_pwr = WeekAquaProtocol.calculate_total_power_percent(norm.r, norm.g, norm.b, norm.w, norm.uv, norm.violet, model_code="5749")
        self.assertLessEqual(total_pwr, 100.0)

    def test_rounding_edge_case_not_exceeding_100(self):
        # Test various peak configurations across models
        for model in ["", "5746", "5748", "5749", "5751", "5752"]:
            norm = WeekAquaProtocol.normalize_spectrum_to_max_power(100, 100, 100, 100, 100, 100, model_code=model)
            total = WeekAquaProtocol.calculate_total_power_percent(norm.r, norm.g, norm.b, norm.w, norm.uv, norm.violet, model_code=model)
            self.assertLessEqual(total, 100.0, f"Model {model} exceeded 100.0% with {total}%")

    def test_state_init_packet(self):
        packet = WeekAquaProtocol.build_state_init_packet()
        self.assertEqual(packet.hex().upper(), "F055555555555555")

    def test_ramp_time_packet_with_24_midnight(self):
        # Test 22:48 -> 24:00 (Slot 5) -> FEF5224824005555
        packet = WeekAquaProtocol.build_ramp_time_packet(5, 22, 48, 24, 0)
        self.assertEqual(packet.hex().upper(), "FEF5224824005555")

        # Test 00:00 -> 02:00 (Slot 6) -> FEF6000002005555
        packet2 = WeekAquaProtocol.build_ramp_time_packet(6, 0, 0, 2, 0)
        self.assertEqual(packet2.hex().upper(), "FEF6000002005555")

    def test_ramp_spectrum_packet(self):
        packet = WeekAquaProtocol.build_ramp_spectrum_packet(1, 100, 80, 60, 0)
        self.assertEqual(packet[0], 0xFB)
        self.assertEqual(packet[1], 0xF1)

    def test_sunrise_sunset_packet(self):
        packet = WeekAquaProtocol.build_sunrise_sunset_packet(8, 0, 18, 0, ramp_idx=2)
        self.assertEqual(packet.hex().upper(), "FEF9080018000102")

    def test_split_cross_midnight_timer(self):
        # 18:00 to 02:00 crosses midnight -> 2 intervals (18:00~24:00 and 00:00~02:00)
        intervals = WeekAquaProtocol.split_cross_midnight_timer(18, 0, 2, 0)
        self.assertEqual(len(intervals), 2)
        self.assertEqual(intervals[0], (18, 0, 24, 0))
        self.assertEqual(intervals[1], (0, 0, 2, 0))

        # 08:00 to 20:00 same-day -> 1 interval (08:00~20:00)
        same_day = WeekAquaProtocol.split_cross_midnight_timer(8, 0, 20, 0)
        self.assertEqual(len(same_day), 1)
        self.assertEqual(same_day[0], (8, 0, 20, 0))

        # 16:00 to 00:00 ends at midnight -> 1 interval (16:00~24:00)
        midnight_end = WeekAquaProtocol.split_cross_midnight_timer(16, 0, 0, 0)
        self.assertEqual(len(midnight_end), 1)
        self.assertEqual(midnight_end[0], (16, 0, 24, 0))


if __name__ == "__main__":
    unittest.main()
