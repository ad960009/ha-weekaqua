"""Config flow for WeekAqua Bluetooth integration."""

from __future__ import annotations
import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak, async_discovered_service_info
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import DOMAIN, SERVICE_UUID, CONF_MAC, CONF_NAME, CONF_MODEL_CODE, DEFAULT_NAME, MODEL_NAMES

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

    def _get_active_reconfigure_entry(self) -> config_entries.ConfigEntry | None:
        """Helper to get the current reconfigure entry safely across HA versions."""
        if hasattr(self, "_get_reconfigure_entry"):
            try:
                return self._get_reconfigure_entry()
            except Exception:
                pass
        entry_id = self.context.get("entry_id")
        if entry_id:
            return self.hass.config_entries.async_get_entry(entry_id)
        return None

    async def async_step_bluetooth(self, discovery_info: BluetoothServiceInfoBleak) -> FlowResult:
        """Handle bluetooth discovery by Home Assistant."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        mac_clean = discovery_info.address.replace(":", "").upper()
        _, model_code = is_matching_weekaqua(discovery_info)
        raw_name = (discovery_info.name or "").strip()
        if not raw_name or raw_name.replace(":", "").upper() == mac_clean:
            pretty_name = f"WeekAqua {MODEL_NAMES.get(model_code, 'Light')}"
        else:
            pretty_name = raw_name

        self.context["title_placeholders"] = {"name": pretty_name}
        self._discovery_info = discovery_info
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Confirm discovery of a WeekAqua device."""
        assert self._discovery_info is not None

        _, model_code = is_matching_weekaqua(self._discovery_info)
        mac_clean = self._discovery_info.address.replace(":", "").upper()
        raw_name = (self._discovery_info.name or "").strip()
        if not raw_name or raw_name.replace(":", "").upper() == mac_clean:
            pretty_name = f"WeekAqua {MODEL_NAMES.get(model_code, 'Light')}"
        else:
            pretty_name = raw_name

        if user_input is not None:
            return self.async_create_entry(
                title=user_input.get(CONF_NAME, pretty_name),
                data={
                    CONF_MAC: self._discovery_info.address,
                    CONF_NAME: user_input.get(CONF_NAME, pretty_name),
                    CONF_MODEL_CODE: model_code,
                },
            )

        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": pretty_name, "address": self._discovery_info.address},
            data_schema=vol.Schema({
                vol.Optional(CONF_NAME, default=pretty_name): str,
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
                mac_clean = service_info.address.replace(":", "").upper()
                raw_name = (service_info.name or "").strip()
                if not raw_name or raw_name.replace(":", "").upper() == mac_clean:
                    name_part = f"WeekAqua {MODEL_NAMES.get(model, 'Light')}"
                else:
                    name_part = raw_name
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

        model_choices = {code: f"{name} ({code})" for code, name in MODEL_NAMES.items()}
        model_choices[""] = "자동 감지 / 기본값"

        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema({
                vol.Required(CONF_MAC, default="AA:BB:CC:11:22:33"): str,
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Optional(CONF_MODEL_CODE, default=""): vol.In(model_choices),
            }),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle reconfiguration of an existing WeekAqua integration entry (Bluetooth & Model migration)."""
        entry = self._get_active_reconfigure_entry()
        if entry is None:
            return self.async_abort(reason="reconfigure_failed")

        errors: dict[str, str] = {}
        current_mac = entry.data.get(CONF_MAC, "")
        current_name = entry.data.get(CONF_NAME, entry.title or DEFAULT_NAME)
        current_model = entry.data.get(CONF_MODEL_CODE, "")

        if user_input is not None:
            chosen_address = user_input.get(CONF_MAC, "").strip()

            if chosen_address == "manual":
                return await self.async_step_reconfigure_manual()

            formatted_mac = format_and_validate_mac(chosen_address)
            if not formatted_mac:
                errors["base"] = "invalid_mac"
            else:
                # Determine new model code: user-selected or auto-detected from scan
                selected_model = user_input.get(CONF_MODEL_CODE, "")
                if not selected_model:
                    selected_model = self._discovered_models.get(formatted_mac, current_model)

                new_name = user_input.get(CONF_NAME, current_name)

                return await self._async_apply_reconfiguration(
                    entry=entry,
                    new_mac=formatted_mac,
                    new_name=new_name,
                    new_model=selected_model,
                )

        # Scan for nearby Bluetooth devices
        self._discovered_devices = {}
        self._discovered_models = {}
        scanned_infos = list(async_discovered_service_info(self.hass, connectable=True))
        known_addresses = {s.address for s in scanned_infos}
        for passive_info in async_discovered_service_info(self.hass, connectable=False):
            if passive_info.address not in known_addresses:
                scanned_infos.append(passive_info)

        # Always include the currently configured device in options
        current_model_name = MODEL_NAMES.get(current_model, "Light")
        options = {
            current_mac: f"📌 현재 등록된 기기: {current_name} ({current_mac}) [{current_model_name}]"
        }

        for service_info in scanned_infos:
            is_match, model = is_matching_weekaqua(service_info)
            if is_match:
                mac_clean = service_info.address.replace(":", "").upper()
                raw_name = (service_info.name or "").strip()
                if not raw_name or raw_name.replace(":", "").upper() == mac_clean:
                    name_part = f"WeekAqua {MODEL_NAMES.get(model, 'Light')}"
                else:
                    name_part = raw_name
                rssi_str = f" [RSSI: {service_info.rssi}dBm]" if service_info.rssi is not None else ""
                display_label = f"{name_part} ({service_info.address}){rssi_str}"
                self._discovered_devices[service_info.address] = display_label
                if model:
                    self._discovered_models[service_info.address] = model
                if service_info.address != current_mac:
                    options[service_info.address] = display_label

        options["manual"] = "✏️ 수동으로 MAC / 모델 직접 입력하기..."

        model_choices = {code: f"{name} ({code})" for code, name in MODEL_NAMES.items()}
        model_choices[""] = "자동 감지 / 기존 모델 유지"

        return self.async_show_form(
            step_id="reconfigure",
            description_placeholders={
                "current_name": current_name,
                "current_mac": current_mac,
                "current_model": current_model_name,
            },
            data_schema=vol.Schema({
                vol.Required(CONF_MAC, default=current_mac): vol.In(options),
                vol.Optional(CONF_NAME, default=current_name): str,
                vol.Optional(CONF_MODEL_CODE, default=current_model): vol.In(model_choices),
            }),
            errors=errors,
        )

    async def async_step_reconfigure_manual(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle manual input for reconfiguration."""
        entry = self._get_active_reconfigure_entry()
        if entry is None:
            return self.async_abort(reason="reconfigure_failed")

        errors: dict[str, str] = {}
        current_mac = entry.data.get(CONF_MAC, "")
        current_name = entry.data.get(CONF_NAME, entry.title or DEFAULT_NAME)
        current_model = entry.data.get(CONF_MODEL_CODE, "")

        if user_input is not None:
            raw_mac = user_input.get(CONF_MAC, "")
            formatted_mac = format_and_validate_mac(raw_mac)
            if not formatted_mac:
                errors["base"] = "invalid_mac"
            else:
                new_model = user_input.get(CONF_MODEL_CODE, current_model)
                new_name = user_input.get(CONF_NAME, current_name)

                return await self._async_apply_reconfiguration(
                    entry=entry,
                    new_mac=formatted_mac,
                    new_name=new_name,
                    new_model=new_model,
                )

        model_choices = {code: f"{name} ({code})" for code, name in MODEL_NAMES.items()}
        model_choices[""] = "기존 모델 유지"

        return self.async_show_form(
            step_id="reconfigure_manual",
            description_placeholders={
                "current_name": current_name,
                "current_mac": current_mac,
            },
            data_schema=vol.Schema({
                vol.Required(CONF_MAC, default=current_mac): str,
                vol.Optional(CONF_NAME, default=current_name): str,
                vol.Optional(CONF_MODEL_CODE, default=current_model): vol.In(model_choices),
            }),
            errors=errors,
        )

    async def _async_apply_reconfiguration(
        self,
        entry: config_entries.ConfigEntry,
        new_mac: str,
        new_name: str,
        new_model: str,
    ) -> FlowResult:
        """Apply reconfiguration, migrate entity/device registries, and reload the integration."""
        old_mac = entry.data.get(CONF_MAC, "")
        old_model = entry.data.get(CONF_MODEL_CODE, "")

        # 1. Verify that new_mac is not already used by another entry
        if new_mac != old_mac:
            for other_entry in self.hass.config_entries.async_entries(DOMAIN):
                if other_entry.entry_id != entry.entry_id and other_entry.unique_id == new_mac:
                    return self.async_abort(reason="already_configured")

        # 2. Migrate Entity Registry: update unique_id so entity_ids remain unchanged
        ent_reg = er.async_get(self.hass)
        existing_entities = er.async_entries_for_config_entry(ent_reg, entry.entry_id)

        if new_mac != old_mac and old_mac:
            _LOGGER.info(
                "WeekAqua Reconfigure: Migrating entity unique_ids from %s to %s for entry %s",
                old_mac, new_mac, entry.entry_id
            )
            for ent in existing_entities:
                if ent.unique_id and old_mac in ent.unique_id:
                    new_unique_id = ent.unique_id.replace(old_mac, new_mac)
                    ent_reg.async_update_entity(ent.entity_id, new_unique_id=new_unique_id)

        # 3. Model Migration: Adjust channel entity availability (disabled_by) based on hardware model
        if new_model != old_model:
            _LOGGER.info(
                "WeekAqua Reconfigure: Model changed from '%s' to '%s'",
                old_model, new_model
            )
            is_old_4ch = old_model in ("5745", "5746", "")
            is_new_4ch = new_model in ("5745", "5746", "")

            target_mac_for_lookup = new_mac if new_mac else old_mac

            # Refresh entity list after possible unique_id update
            current_entities = er.async_entries_for_config_entry(ent_reg, entry.entry_id)
            for ent in current_entities:
                # White Channel handling
                if ent.unique_id and ent.unique_id.endswith("_white"):
                    if is_old_4ch and not is_new_4ch:
                        # Switched from 4CH (RGB/UV) to RGBW/Multi-channel -> Enable White channel
                        if ent.disabled_by is not None:
                            ent_reg.async_update_entity(ent.entity_id, disabled_by=None)
                    elif not is_old_4ch and is_new_4ch:
                        # Switched to 4CH (RGB/UV) -> Disable White channel to prevent light leak
                        if ent.disabled_by is None:
                            ent_reg.async_update_entity(
                                ent.entity_id, disabled_by=er.RegistryEntryDisabler.INTEGRATION
                            )

                # Violet Channel handling for 6CH / Marine / Advanced models
                if ent.unique_id and ent.unique_id.endswith("_violet"):
                    if new_model in ("5748", "5749", "5751", "5752"):
                        if ent.disabled_by is not None:
                            ent_reg.async_update_entity(ent.entity_id, disabled_by=None)

        # 4. Device Registry Migration: update device identifiers, connections, name, and model
        dev_reg = dr.async_get(self.hass)
        device_lookup_mac = old_mac if old_mac else new_mac
        device = dev_reg.async_get_device(identifiers={(DOMAIN, device_lookup_mac)})
        if device is not None:
            update_kwargs: dict[str, Any] = {
                "name": new_name,
                "model": f"WeekAqua ({new_model or 'BLE'})",
            }
            if new_mac != old_mac:
                update_kwargs["new_identifiers"] = {(DOMAIN, new_mac)}
                update_kwargs["new_connections"] = {(dr.CONNECTION_BLUETOOTH, new_mac)}

            dev_reg.async_update_device(device.id, **update_kwargs)

        # 5. Update ConfigEntry and trigger instant reload
        return self.async_update_reload_and_abort(
            entry,
            unique_id=new_mac,
            title=new_name,
            data={
                CONF_MAC: new_mac,
                CONF_NAME: new_name,
                CONF_MODEL_CODE: new_model,
            },
            reason="reconfigure_successful",
        )
