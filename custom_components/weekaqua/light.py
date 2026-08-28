"""Light platform for WeekAqua."""

from __future__ import annotations
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_RGBW_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import WeekAquaCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up WeekAqua light entity."""
    coordinator: WeekAquaCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([WeekAquaLight(coordinator, entry)])


class WeekAquaLight(CoordinatorEntity[WeekAquaCoordinator], LightEntity):
    """Representation of the Master WeekAqua Aquarium Light."""

    _attr_has_entity_name = True
    _attr_color_mode = ColorMode.RGBW
    _attr_supported_color_modes = {ColorMode.RGBW}

    def __init__(self, coordinator: WeekAquaCoordinator, entry: ConfigEntry) -> None:
        """Initialize the light."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{coordinator.mac}_light"
        self._attr_name = "Aquarium Light"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.mac)},
            connections={(CONNECTION_BLUETOOTH, self.coordinator.mac)},
            name=self.coordinator.display_name,
            manufacturer="WeekAqua",
            model=self.coordinator.model_name,
        )

    @property
    def is_on(self) -> bool:
        """Return True if any channel has output > 0."""
        return (
            self.coordinator.current_r > 0
            or self.coordinator.current_g > 0
            or self.coordinator.current_b > 0
            or self.coordinator.current_w > 0
            or self.coordinator.current_uv > 0
            or self.coordinator.current_v > 0
        )

    @property
    def brightness(self) -> int:
        """Return 0~255 master brightness based on maximum channel output."""
        if self._is_4ch_rgb_uv():
            max_ch = max(
                self.coordinator.current_r,
                self.coordinator.current_g,
                self.coordinator.current_b,
                self.coordinator.current_uv,
            )
        else:
            max_ch = max(
                self.coordinator.current_r,
                self.coordinator.current_g,
                self.coordinator.current_b,
                self.coordinator.current_w,
                self.coordinator.current_uv,
                self.coordinator.current_v,
            )
        return int(round(max_ch * 2.55))

    @property
    def rgbw_color(self) -> tuple[int, int, int, int]:
        """Return current RGBW channel intensities scaled to 0-255 (Channel 4 maps to UV for 4CH RGB/UV)."""
        w_or_uv = self.coordinator.current_uv if self._is_4ch_rgb_uv() else self.coordinator.current_w
        return (
            int(round(self.coordinator.current_r * 2.55)),
            int(round(self.coordinator.current_g * 2.55)),
            int(round(self.coordinator.current_b * 2.55)),
            int(round(w_or_uv * 2.55)),
        )

    def _is_4ch_rgb_uv(self) -> bool:
        """Detect if device is a 4-channel RGB/UV light (M800 Pro, M600, S-Series, T90, etc.)."""
        code = self.coordinator.model_code
        if code in ("5748", "5749", "5750", "5751", "5752"):
            return False
        names = [
            (self.coordinator.ble_name or "").upper(),
            (self.coordinator.device_name or "").upper(),
            (self.coordinator.display_name or "").upper(),
        ]
        for name in names:
            if any(w in name for w in ("6CH", "10CH", "MARINE", "CORAL", "A-SERIES", "A430")):
                return False
            if any(w in name for w in ("UV", "UVA", "RGB/UV", "RGB-UV", "RGB_UV", "M800", "M600", "M450", "M400", "M900", "M1200", "M-PRO", "M PRO", "MPRO", "S400", "S600", "S800", "S1200", "T90", "T60", "Z400", "Z600", "P600", "P800", "P900", "P1200")) or name.startswith("M"):
                return True
        return code == "5746"

    def _has_white(self) -> bool:
        """Detect if device has physical White channel."""
        if self._is_4ch_rgb_uv():
            return False
        return True

    def _has_uv(self) -> bool:
        """Detect if device has UV/UVA channel."""
        code = self.coordinator.model_code
        if code in ("5748", "5749", "5750", "5751", "5752"):
            return True
        names = [
            (self.coordinator.ble_name or "").upper(),
            (self.coordinator.device_name or "").upper(),
            (self.coordinator.display_name or "").upper(),
        ]
        for name in names:
            if any(w in name for w in ("6CH", "10CH", "MARINE", "CORAL", "A-SERIES", "A430", "UV", "UVA")):
                return True
        return self._is_4ch_rgb_uv()

    def _has_6ch(self) -> bool:
        """Detect if device has 6 or more channels (Violet)."""
        code = self.coordinator.model_code
        if code in ("5749", "5750", "5751", "5752"):
            return True
        names = [
            (self.coordinator.ble_name or "").upper(),
            (self.coordinator.device_name or "").upper(),
            (self.coordinator.display_name or "").upper(),
        ]
        for name in names:
            if any(w in name for w in ("6CH", "10CH")):
                return True
        return False

    def _max_slots(self) -> int:
        """Detect maximum hardware schedule slots for model (5, 8, or 12)."""
        code = self.coordinator.model_code
        if code == "5745":
            return 5
        elif code in ("5747", "5748", "5752"):
            return 12
        elif code in ("5746", "5749", "5751"):
            return 8
        names = [
            (self.coordinator.ble_name or "").upper(),
            (self.coordinator.device_name or "").upper(),
            (self.coordinator.display_name or "").upper(),
        ]
        for name in names:
            if any(w in name for w in ("6CH", "10CH", "MARINE", "CORAL", "A430")):
                return 12
        return 8

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes for card and automations."""
        ble_n = self.coordinator.ble_name
        disp_n = self.coordinator.display_name
        return {
            "r": self.coordinator.current_r,
            "g": self.coordinator.current_g,
            "b": self.coordinator.current_b,
            "w": self.coordinator.current_w,
            "uv": self.coordinator.current_uv,
            "v": self.coordinator.current_v,
            "fan": self.coordinator.current_fan,
            "power_pct": self.coordinator.total_power_pct,
            "connected": self.coordinator.is_connected,
            "schedule_enabled": self.coordinator.schedule_enabled,
            "schedule_points": self.coordinator.schedule_points,
            "schedule_meta": getattr(self.coordinator, "schedule_meta", {}),
            "model_code": self.coordinator.model_code,
            "device_name": ble_n or disp_n,
            "ble_name": ble_n,
            "model_name": ble_n or disp_n,
            "mac": self.coordinator.mac,
            "is_4ch_rgb_uv": self._is_4ch_rgb_uv(),
            "has_white": self._has_white(),
            "has_uv": self._has_uv(),
            "has_6ch": self._has_6ch(),
            "max_slots": self._max_slots(),
            "keep_moonlight": self.coordinator.keep_moonlight,
            "moonlight_brightness": self.coordinator.moonlight_brightness,
            "current_mode": self.coordinator._current_mode,
            "mode_name": "Schedule (Mode 2)" if self.coordinator._current_mode == 2 else "Live (Mode 1)",
            "ble_logs": list(self.coordinator.ble_logs),
            "queue_size": self.coordinator._write_queue.qsize(),
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the light or apply requested color/brightness."""
        if ATTR_RGBW_COLOR in kwargs:
            rgbw = kwargs[ATTR_RGBW_COLOR]
            r = rgbw[0] / 2.55
            g = rgbw[1] / 2.55
            b = rgbw[2] / 2.55
            w_or_uv = rgbw[3] / 2.55
            if self._is_4ch_rgb_uv():
                await self.coordinator.async_set_spectrum(r, g, b, 0.0, uv=w_or_uv, violet=0.0)
            else:
                await self.coordinator.async_set_spectrum(r, g, b, w_or_uv, self.coordinator.current_uv, self.coordinator.current_v)
        elif ATTR_BRIGHTNESS in kwargs:
            target_scale = kwargs[ATTR_BRIGHTNESS] / 255.0
            cur_max = max(1.0, self.brightness / 2.55)
            ratio = (target_scale * 100.0) / cur_max
            await self.coordinator.async_set_spectrum(
                self.coordinator.current_r * ratio,
                self.coordinator.current_g * ratio,
                self.coordinator.current_b * ratio,
                self.coordinator.current_w * ratio,
                self.coordinator.current_uv * ratio,
                self.coordinator.current_v * ratio,
            )
        else:
            # Re-enable dynamic schedule or turn to last set spectrum
            await self.coordinator.async_set_schedule_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off all light channels."""
        await self.coordinator.async_set_spectrum(0, 0, 0, 0, 0, 0, disable_schedule=True)
