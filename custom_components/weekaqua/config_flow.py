"""Config flow for WeekAqua Bluetooth integration."""

from __future__ import annotations
import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak, async_discovered_service_info
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, SERVICE_UUID, CONF_MAC, CONF_NAME, CONF_MODEL_CODE, DEFAULT_NAME

_LOGGER = logging.getLogger(__name__)

MAC_REGEX = re.compile(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$")


def is_matching_weekaqua(service_info: BluetoothServiceInfoBleak) -> tuple[bool, str]:
    """Check if discovered Bluetooth device matches WeekAqua criteria (matching WPF BleService)."""
    model_code = ""

    # 1. Check Model Code in Manufacturer Data (5745 ~ 5752)
    if service_info.manufacturer_data:
        for m_id, m_data in service_info.manufacturer_data.items():
            hex_str = m_data.hex().upper()
            for target in ("5752", "5751", "5750", "5749", "5748", "5747", "5746", "5745"):
                if target in hex_str:
                    model_code = target
                    return True, model_code

    # 2. Check Service UUIDs (FFE0, FFF0, FF60)
    for u in service_info.service_uuids:
        u_upper = u.upper()
        if any(uuid_part in u_upper for uuid_part in ("FFE0", "FFF0", "FF60")):
            return True, model_code

    # 3. Check LocalName (matching official WPF keywords & regex)
    name = (service_info.name or "").upper()
    if name:
        weekaqua_keywords = (
            "WEEK", "AQUA", "LIGHT", "LAMP", "PLUG", "SOCKET", "SP0",
            "M-", "S-", "T-", "A-", "L-", "T90", "T60", "T80", "T120", "T45",
            "M450", "M600", "M800", "M900", "M1200", "M-PRO", "M PRO", "M_PRO",
            "S400", "S450", "S600", "S800", "S900", "S1200", "S-PRO", "S PRO", "S_PRO",
            "CORAL", "MARINE", "Z400", "Z600", "Z800", "P600", "P800", "P900", "P1200"
        )
        if any(kw in name for kw in weekaqua_keywords):
            return True, model_code
        if re.search(r"\b[MSTZPAL][0-9]{2,4}", name):
            return True, model_code

    return False, model_code


def format_and_validate_mac(raw_mac: str) -> str | None:
    """Format and validate MAC address string to standard uppercase format AA:BB:CC:11:22:33."""
    clean = raw_mac.strip().replace("-", ":").replace(".", ":").upper()
    # Handle contiguous 12-char hex string (e.g. AABBCC112233)
    if len(clean) == 12 and all(c in "0123456789ABCDEF" for c in clean):
        clean = ":".join(clean[i:i+2] for i in range(0, 12, 2))
    if MAC_REGEX.match(clean):
        return clean
    return None


class WeekAquaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for WeekAqua."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, str] = {}
        self._discovered_models: dict[str, str] = {}

    async def async_step_bluetooth(self, discovery_info: BluetoothServiceInfoBleak) -> FlowResult:
        """Handle bluetooth discovery by Home Assistant."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        self.context["title_placeholders"] = {"name": discovery_info.name}
        self._discovery_info = discovery_info
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Confirm discovery of a WeekAqua device."""
        assert self._discovery_info is not None

        if user_input is not None:
            _, model_code = is_matching_weekaqua(self._discovery_info)
            return self.async_create_entry(
                title=user_input.get(CONF_NAME, self._discovery_info.name or DEFAULT_NAME),
                data={
                    CONF_MAC: self._discovery_info.address,
                    CONF_NAME: user_input.get(CONF_NAME, self._discovery_info.name or DEFAULT_NAME),
                    CONF_MODEL_CODE: model_code,
                },
            )

        name = self._discovery_info.name or DEFAULT_NAME
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": name, "address": self._discovery_info.address},
            data_schema=vol.Schema({
                vol.Optional(CONF_NAME, default=name): str,
            }),
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle user-initiated setup (scanned dropdown selection or manual MAC input)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            chosen_address = user_input.get(CONF_MAC, "").strip()

            if chosen_address == "manual":
                return await self.async_step_manual()

            formatted_mac = format_and_validate_mac(chosen_address)
            if not formatted_mac:
                errors["base"] = "invalid_mac"
            else:
                await self.async_set_unique_id(formatted_mac)
                self._abort_if_unique_id_configured()

                dev_name = self._discovered_devices.get(formatted_mac)
                if not dev_name:
                    dev_name = user_input.get(CONF_NAME) or f"WeekAqua ({formatted_mac})"
                else:
                    dev_name = dev_name.split(" [RSSI")[0].strip()

                model_code = self._discovered_models.get(formatted_mac, "")
                return self.async_create_entry(
                    title=dev_name,
                    data={
                        CONF_MAC: formatted_mac,
                        CONF_NAME: dev_name,
                        CONF_MODEL_CODE: model_code,
                    },
                )

        # Scan and populate matching WeekAqua devices via HA Bluetooth backend
        self._discovered_devices = {}
        self._discovered_models = {}
        scanned_infos = list(async_discovered_service_info(self.hass, connectable=True))
        known_addresses = {s.address for s in scanned_infos}
        for passive_info in async_discovered_service_info(self.hass, connectable=False):
            if passive_info.address not in known_addresses:
                scanned_infos.append(passive_info)

        for service_info in scanned_infos:
            is_match, model = is_matching_weekaqua(service_info)
            if is_match:
                name_part = service_info.name or "WeekAqua Light"
                rssi_str = f" [RSSI: {service_info.rssi}dBm]" if service_info.rssi is not None else ""
                display_label = f"{name_part} ({service_info.address}){rssi_str}"
                self._discovered_devices[service_info.address] = display_label
                if model:
                    self._discovered_models[service_info.address] = model

        if self._discovered_devices:
            options = {addr: label for addr, label in self._discovered_devices.items()}
            options["manual"] = "✏️ 수동으로 MAC 주소 직접 입력하기..."

            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({
                    vol.Required(CONF_MAC): vol.In(options),
                    vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
                }),
                errors=errors,
            )

        # Fallback to manual entry if no devices scanned yet
        return await self.async_step_manual()

    async def async_step_manual(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle manual MAC address entry."""
        errors: dict[str, str] = {}

        if user_input is not None:
            raw_mac = user_input.get(CONF_MAC, "")
            formatted_mac = format_and_validate_mac(raw_mac)
            if not formatted_mac:
                errors["base"] = "invalid_mac"
            else:
                await self.async_set_unique_id(formatted_mac)
                self._abort_if_unique_id_configured()

                name = user_input.get(CONF_NAME) or f"WeekAqua ({formatted_mac})"
                return self.async_create_entry(
                    title=name,
                    data={
                        CONF_MAC: formatted_mac,
                        CONF_NAME: name,
                        CONF_MODEL_CODE: user_input.get(CONF_MODEL_CODE, ""),
                    },
                )

        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema({
                vol.Required(CONF_MAC, default="AA:BB:CC:11:22:33"): str,
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
            }),
            errors=errors,
        )
