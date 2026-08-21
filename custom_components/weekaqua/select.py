"""Select platform for WeekAqua."""

from __future__ import annotations
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import WeekAquaCoordinator

MODE_SCHEDULE = "Schedule Mode (Mode 2)"
MODE_LIVE = "Live Mode (Mode 1)"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up WeekAqua select entities."""
    coordinator: WeekAquaCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        WeekAquaModeSelect(coordinator),
    ])


class WeekAquaModeSelect(CoordinatorEntity[WeekAquaCoordinator], SelectEntity, RestoreEntity):
    """Dropdown selector for WeekAqua hardware operating mode."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:tune-vertical"
    _attr_options = [MODE_SCHEDULE, MODE_LIVE]

    def __init__(self, coordinator: WeekAquaCoordinator) -> None:
        """Initialize mode select entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.mac}_operation_mode"
        self._attr_name = "Operation Mode"

    async def async_added_to_hass(self) -> None:
        """Restore previous mode on HA startup."""
        await super().async_added_to_hass()
        if (last_state := await self.async_get_last_state()) is not None:
            if "Schedule" in last_state.state or "Mode 2" in last_state.state:
                self.coordinator._current_mode = 2
            elif "Live" in last_state.state or "Mode 1" in last_state.state:
                self.coordinator._current_mode = 1
            self.coordinator.async_set_updated_data(self.coordinator._build_data())

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.mac)},
            connections={(CONNECTION_BLUETOOTH, self.coordinator.mac)},
            name=self.coordinator.device_name,
            manufacturer="WeekAqua",
            model=f"WeekAqua ({self.coordinator.model_code or 'BLE'})",
        )

    @property
    def current_option(self) -> str:
        """Return current active hardware operating mode."""
        return MODE_SCHEDULE if self.coordinator._current_mode == 2 else MODE_LIVE

    async def async_select_option(self, option: str) -> None:
        """Change the operating mode."""
        if option == MODE_SCHEDULE:
            await self.coordinator.async_activate_schedule_mode()
        else:
            await self.coordinator.async_activate_live_mode()
