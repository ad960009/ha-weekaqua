"""Switch platform for WeekAqua."""

from __future__ import annotations
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import WeekAquaCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up WeekAqua switch entities."""
    coordinator: WeekAquaCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        WeekAquaScheduleSwitch(coordinator),
        WeekAquaMoonlightSwitch(coordinator),
        WeekAquaBleConnectionSwitch(coordinator),
    ])


class WeekAquaBleConnectionSwitch(CoordinatorEntity[WeekAquaCoordinator], SwitchEntity):
    """Switch to monitor and manually connect/disconnect Bluetooth session."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: WeekAquaCoordinator) -> None:
        """Initialize switch."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.mac}_ble_connection"
        self._attr_name = "Bluetooth Connection"

    @property
    def icon(self) -> str:
        """Dynamic icon indicating connection state."""
        return "mdi:bluetooth" if self.coordinator.is_connected else "mdi:bluetooth-off"

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
    def is_on(self) -> bool:
        """Return True if BLE session is connected."""
        return self.coordinator.is_connected

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Connect BLE session."""
        await self.coordinator.async_connect()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disconnect BLE session."""
        await self.coordinator.async_disconnect()


class WeekAquaScheduleSwitch(CoordinatorEntity[WeekAquaCoordinator], SwitchEntity, RestoreEntity):
    """Switch to enable/disable unlimited dynamic schedule."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: WeekAquaCoordinator) -> None:
        """Initialize switch."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.mac}_schedule_enable"
        self._attr_name = "Dynamic Schedule"

    async def async_added_to_hass(self) -> None:
        """Restore previous state on HA startup."""
        await super().async_added_to_hass()
        if (last_state := await self.async_get_last_state()) is not None:
            if last_state.state == "on":
                self.coordinator.schedule_enabled = True
                await self.coordinator.async_set_schedule_enabled(True)
            elif last_state.state == "off":
                self.coordinator.schedule_enabled = False
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
    def is_on(self) -> bool:
        """Return True if schedule is currently running."""
        return self.coordinator.schedule_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable dynamic schedule."""
        await self.coordinator.async_set_schedule_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable dynamic schedule (freeze at current or manual)."""
        await self.coordinator.async_set_schedule_enabled(False)


class WeekAquaMoonlightSwitch(CoordinatorEntity[WeekAquaCoordinator], SwitchEntity, RestoreEntity):
    """Switch to toggle night moonlight retention."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:moon-waning-crescent"

    def __init__(self, coordinator: WeekAquaCoordinator) -> None:
        """Initialize switch."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.mac}_moonlight"
        self._attr_name = "Keep Night Moonlight"

    async def async_added_to_hass(self) -> None:
        """Restore previous state on HA startup."""
        await super().async_added_to_hass()
        if (last_state := await self.async_get_last_state()) is not None:
            self.coordinator.keep_moonlight = (last_state.state == "on")
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
    def is_on(self) -> bool:
        """Return True if moonlight mode is enabled."""
        return self.coordinator.keep_moonlight

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable moonlight."""
        await self.coordinator.async_set_moonlight_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable moonlight."""
        await self.coordinator.async_set_moonlight_enabled(False)
