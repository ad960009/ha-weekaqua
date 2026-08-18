"""Button platform for WeekAqua."""

from __future__ import annotations
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
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
    """Set up WeekAqua button entities."""
    coordinator: WeekAquaCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        WeekAquaConnectButton(coordinator),
        WeekAquaDisconnectButton(coordinator),
    ])


class WeekAquaConnectButton(CoordinatorEntity[WeekAquaCoordinator], ButtonEntity):
    """Button to manually establish BLE connection."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:bluetooth-connect"

    def __init__(self, coordinator: WeekAquaCoordinator) -> None:
        """Initialize button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.mac}_connect_btn"
        self._attr_name = "Connect BLE"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.mac)},
            name=self.coordinator.device_name,
            manufacturer="WeekAqua",
            model=f"WeekAqua ({self.coordinator.model_code or 'BLE'})",
        )

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.coordinator.async_connect()


class WeekAquaDisconnectButton(CoordinatorEntity[WeekAquaCoordinator], ButtonEntity):
    """Button to manually release BLE connection."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:bluetooth-off"

    def __init__(self, coordinator: WeekAquaCoordinator) -> None:
        """Initialize button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.mac}_disconnect_btn"
        self._attr_name = "Disconnect BLE"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.mac)},
            name=self.coordinator.device_name,
            manufacturer="WeekAqua",
            model=f"WeekAqua ({self.coordinator.model_code or 'BLE'})",
        )

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.coordinator.async_disconnect()
