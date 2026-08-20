"""WeekAqua Home Assistant Custom Integration."""

from __future__ import annotations
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv, device_registry as dr, entity_registry as er

from .const import DOMAIN, PRESETS
from .coordinator import WeekAquaCoordinator
from .protocol import WeekAquaProtocol
from .frontend import async_setup_frontend

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.BUTTON,
]

# Service Schemas
SERVICE_APPLY_PRESET = "apply_preset"
SERVICE_SET_SPECTRUM = "set_spectrum"
SERVICE_SET_SCHEDULE = "set_schedule"
SERVICE_SET_TIMER = "set_timer"
SERVICE_SYNC_RTC = "sync_rtc"
SERVICE_CONNECT = "connect"
SERVICE_DISCONNECT = "disconnect"
SERVICE_SET_SCHEDULE_ENABLED = "set_schedule_enabled"

SCHEMA_COMMON_TARGET = {
    vol.Optional("device_id"): cv.string,
    vol.Optional("entity_id"): cv.string,
}

SCHEMA_SET_SCHEDULE_ENABLED = vol.Schema({
    **SCHEMA_COMMON_TARGET,
    vol.Required("enabled"): cv.boolean,
})

SCHEMA_APPLY_PRESET = vol.Schema({
    **SCHEMA_COMMON_TARGET,
    vol.Required("preset"): vol.In(list(PRESETS.keys())),
})

SCHEMA_SET_SPECTRUM = vol.Schema({
    **SCHEMA_COMMON_TARGET,
    vol.Required("red"): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
    vol.Required("green"): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
    vol.Required("blue"): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
    vol.Required("white"): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
    vol.Optional("uv", default=0.0): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
    vol.Optional("violet", default=0.0): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
    vol.Optional("disable_schedule", default=True): cv.boolean,
})

SCHEMA_SET_SCHEDULE = vol.Schema({
    **SCHEMA_COMMON_TARGET,
    vol.Required("points"): vol.All(
        cv.ensure_list,
        [
            vol.Schema({
                vol.Required("time"): cv.string,
                vol.Required("r"): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
                vol.Required("g"): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
                vol.Required("b"): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
                vol.Required("w"): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
                vol.Optional("uv", default=0.0): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
                vol.Optional("v", default=0.0): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
            })
        ],
    ),
    vol.Optional("start_time"): cv.string,
    vol.Optional("end_time"): cv.string,
    vol.Optional("slots"): vol.Coerce(int),
    vol.Optional("preset"): cv.string,
    vol.Optional("keep_moonlight"): cv.boolean,
})

SCHEMA_SET_TIMER = vol.Schema({
    **SCHEMA_COMMON_TARGET,
    vol.Required("start_time"): cv.string,
    vol.Required("end_time"): cv.string,
    vol.Optional("preset"): vol.In(list(PRESETS.keys())),
    vol.Optional("red", default=80.0): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
    vol.Optional("green", default=80.0): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
    vol.Optional("blue", default=80.0): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
    vol.Optional("white", default=80.0): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
    vol.Optional("uv", default=0.0): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
    vol.Optional("violet", default=0.0): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
    vol.Optional("ramp_index", default=2): vol.All(vol.Coerce(int), vol.Range(min=0, max=5)),
})

SCHEMA_TARGET_ONLY = vol.Schema(SCHEMA_COMMON_TARGET)


def _get_target_coordinators(hass: HomeAssistant, call: ServiceCall) -> list[WeekAquaCoordinator]:
    """Find specific target coordinator(s) based on entity_id or device_id in service call."""
    entity_id = call.data.get("entity_id")
    if entity_id:
        state = hass.states.get(entity_id)
        if state and "mac" in state.attributes:
            target_mac = state.attributes["mac"].upper()
            for coord in hass.data[DOMAIN].values():
                if coord.mac.upper() == target_mac:
                    return [coord]
        ent_reg = er.async_get(hass)
        ent_entry = ent_reg.async_get(entity_id)
        if ent_entry and ent_entry.config_entry_id and ent_entry.config_entry_id in hass.data[DOMAIN]:
            return [hass.data[DOMAIN][ent_entry.config_entry_id]]
        for coord in hass.data[DOMAIN].values():
            if coord.mac.replace(":", "").lower() in entity_id.lower():
                return [coord]

    device_id = call.data.get("device_id")
    if device_id:
        dev_reg = dr.async_get(hass)
        device = dev_reg.async_get(device_id)
        if device:
            for entry_id in device.config_entries:
                if entry_id in hass.data[DOMAIN]:
                    return [hass.data[DOMAIN][entry_id]]

    return list(hass.data[DOMAIN].values())


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up WeekAqua from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Automatically serve and register Lovelace dashboard card & copy to www
    await async_setup_frontend(hass)

    coordinator = WeekAquaCoordinator(hass, entry.data, entry=entry)
    await coordinator.async_setup()
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register Custom Services with Target Resolution
    async def handle_apply_preset(call: ServiceCall) -> None:
        preset_key = call.data["preset"]
        if preset_key in PRESETS:
            preset = PRESETS[preset_key]
            for coord in _get_target_coordinators(hass, call):
                await coord.async_set_spectrum(
                    preset["r"], preset["g"], preset["b"], preset["w"],
                    preset.get("uv", 0), preset.get("v", 0)
                )

    async def handle_set_spectrum(call: ServiceCall) -> None:
        r = call.data["red"]
        g = call.data["green"]
        b = call.data["blue"]
        w = call.data["white"]
        uv = call.data.get("uv", 0.0)
        violet = call.data.get("violet", 0.0)
        disable_sched = call.data.get("disable_schedule", True)
        for coord in _get_target_coordinators(hass, call):
            await coord.async_set_spectrum(r, g, b, w, uv, violet, disable_schedule=disable_sched)

    async def handle_set_schedule(call: ServiceCall) -> None:
        points = call.data["points"]
        meta = {
            "start_time": call.data.get("start_time"),
            "end_time": call.data.get("end_time"),
            "slots": call.data.get("slots"),
            "preset": call.data.get("preset"),
            "keep_moonlight": call.data.get("keep_moonlight"),
        }
        for coord in _get_target_coordinators(hass, call):
            await coord.async_set_schedule(points, meta=meta)

    async def handle_set_timer(call: ServiceCall) -> None:
        start_time = call.data["start_time"]
        end_time = call.data["end_time"]
        preset_key = call.data.get("preset")
        if preset_key and preset_key in PRESETS:
            p = PRESETS[preset_key]
            r = p["r"]
            g = p["g"]
            b = p["b"]
            w = p["w"]
            uv = p.get("uv", 0.0)
            violet = p.get("v", 0.0)
        else:
            r = call.data.get("red", 80.0)
            g = call.data.get("green", 80.0)
            b = call.data.get("blue", 80.0)
            w = call.data.get("white", 80.0)
            uv = call.data.get("uv", 0.0)
            violet = call.data.get("violet", 0.0)
        ramp_idx = call.data.get("ramp_index", 2)

        for coord in _get_target_coordinators(hass, call):
            await coord.async_set_hardware_timer(
                start_time, end_time, r, g, b, w, uv, violet, ramp_idx=ramp_idx
            )

    async def handle_sync_rtc(call: ServiceCall) -> None:
        for coord in _get_target_coordinators(hass, call):
            await coord.enqueue_packet(WeekAquaProtocol.build_rtc_sync_packet())

    async def handle_connect(call: ServiceCall) -> None:
        for coord in _get_target_coordinators(hass, call):
            await coord.async_connect()

    async def handle_disconnect(call: ServiceCall) -> None:
        for coord in _get_target_coordinators(hass, call):
            await coord.async_disconnect()

    async def handle_set_schedule_enabled(call: ServiceCall) -> None:
        enabled = call.data["enabled"]
        for coord in _get_target_coordinators(hass, call):
            await coord.async_set_schedule_enabled(enabled)

    if not hass.services.has_service(DOMAIN, SERVICE_APPLY_PRESET):
        hass.services.async_register(DOMAIN, SERVICE_APPLY_PRESET, handle_apply_preset, schema=SCHEMA_APPLY_PRESET)
        hass.services.async_register(DOMAIN, SERVICE_SET_SPECTRUM, handle_set_spectrum, schema=SCHEMA_SET_SPECTRUM)
        hass.services.async_register(DOMAIN, SERVICE_SET_SCHEDULE, handle_set_schedule, schema=SCHEMA_SET_SCHEDULE)
        hass.services.async_register(DOMAIN, SERVICE_SET_TIMER, handle_set_timer, schema=SCHEMA_SET_TIMER)
        hass.services.async_register(DOMAIN, SERVICE_SYNC_RTC, handle_sync_rtc, schema=SCHEMA_TARGET_ONLY)
        hass.services.async_register(DOMAIN, SERVICE_CONNECT, handle_connect, schema=SCHEMA_TARGET_ONLY)
        hass.services.async_register(DOMAIN, SERVICE_DISCONNECT, handle_disconnect, schema=SCHEMA_TARGET_ONLY)
        hass.services.async_register(DOMAIN, SERVICE_SET_SCHEDULE_ENABLED, handle_set_schedule_enabled, schema=SCHEMA_SET_SCHEDULE_ENABLED)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator: WeekAquaCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
    await coordinator.async_unload()

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
