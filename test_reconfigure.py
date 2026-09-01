"""Unit tests for WeekAqua Reconfiguration & Entity/Device Migration Flow without requiring full HA install."""

import asyncio
import os
import re
import sys
import unittest
from types import ModuleType
from unittest.mock import MagicMock

# Setup mock BLE packages
mock_bleak = ModuleType("bleak")
mock_bleak.BleakClient = MagicMock
mock_bleak_exc = ModuleType("bleak.exc")
mock_bleak_exc.BleakError = Exception
sys.modules["bleak"] = mock_bleak
sys.modules["bleak.exc"] = mock_bleak_exc

mock_brc = ModuleType("bleak_retry_connector")
mock_brc.BleakClientWithServiceCache = MagicMock
mock_brc.establish_connection = MagicMock
sys.modules["bleak_retry_connector"] = mock_brc

# Setup mock homeassistant package structure
ha_pkg = ModuleType("homeassistant")
ha_pkg.__path__ = []
sys.modules["homeassistant"] = ha_pkg

mock_const = ModuleType("homeassistant.const")
mock_const.Platform = MagicMock()
mock_const.PERCENTAGE = "%"
sys.modules["homeassistant.const"] = mock_const
ha_pkg.const = mock_const

mock_config_entries = ModuleType("homeassistant.config_entries")
class MockConfigFlow:
    def __init_subclass__(cls, **kwargs):
        pass

    def __init__(self):
        self.hass = MagicMock()
        self.context = {}

    async def async_set_unique_id(self, unique_id):
        self.unique_id = unique_id

    def _abort_if_unique_id_configured(self):
        pass

    def async_abort(self, reason):
        return {"type": "abort", "reason": reason}

    def async_show_form(self, step_id, data_schema=None, description_placeholders=None, errors=None):
        return {
            "type": "form",
            "step_id": step_id,
            "data_schema": data_schema,
            "description_placeholders": description_placeholders,
            "errors": errors or {},
        }

    def async_create_entry(self, title, data):
        return {
            "type": "create_entry",
            "title": title,
            "data": data,
        }

    def async_update_reload_and_abort(self, entry, unique_id=None, title=None, data=None, reason="reconfigure_successful"):
        if unique_id:
            entry.unique_id = unique_id
        if title:
            entry.title = title
        if data:
            entry.data = data
        return {
            "type": "abort",
            "reason": reason,
        }

mock_config_entries.ConfigFlow = MockConfigFlow
mock_config_entries.ConfigEntry = MagicMock
sys.modules["homeassistant.config_entries"] = mock_config_entries
ha_pkg.config_entries = mock_config_entries

components_pkg = ModuleType("homeassistant.components")
components_pkg.__path__ = []
sys.modules["homeassistant.components"] = components_pkg

mock_bluetooth = ModuleType("homeassistant.components.bluetooth")
mock_bluetooth.BluetoothServiceInfoBleak = MagicMock
mock_bluetooth.async_discovered_service_info = MagicMock(return_value=[])
sys.modules["homeassistant.components.bluetooth"] = mock_bluetooth

mock_frontend = ModuleType("homeassistant.components.frontend")
mock_frontend.add_extra_js_url = MagicMock()
sys.modules["homeassistant.components.frontend"] = mock_frontend

mock_http = ModuleType("homeassistant.components.http")
mock_http.StaticPathConfig = MagicMock()
sys.modules["homeassistant.components.http"] = mock_http

mock_data_entry_flow = ModuleType("homeassistant.data_entry_flow")
mock_data_entry_flow.FlowResult = dict
sys.modules["homeassistant.data_entry_flow"] = mock_data_entry_flow

mock_helpers = ModuleType("homeassistant.helpers")
mock_dr = ModuleType("homeassistant.helpers.device_registry")
mock_dr.CONNECTION_BLUETOOTH = "bluetooth"
mock_dr.async_get = MagicMock()
mock_dr.async_get_device = MagicMock()
mock_dr.async_update_device = MagicMock()
sys.modules["homeassistant.helpers.device_registry"] = mock_dr

mock_er = ModuleType("homeassistant.helpers.entity_registry")
mock_er.RegistryEntryDisabler = MagicMock()
mock_er.RegistryEntryDisabler.INTEGRATION = "integration"
mock_er.async_get = MagicMock()
mock_er.async_entries_for_config_entry = MagicMock()
mock_er.async_update_entity = MagicMock()
sys.modules["homeassistant.helpers.entity_registry"] = mock_er
sys.modules["homeassistant.helpers"] = mock_helpers

mock_vol = ModuleType("voluptuous")
class MockSchema:
    def __init__(self, schema):
        self.schema = schema
mock_vol.Schema = MockSchema
mock_vol.Required = lambda k, default=None: k
mock_vol.Optional = lambda k, default=None: k
mock_vol.In = lambda options: options
mock_vol.All = lambda *args: args[0]
mock_vol.Coerce = lambda t: t
mock_vol.Range = lambda **kwargs: kwargs
sys.modules["voluptuous"] = mock_vol

mock_core = ModuleType("homeassistant.core")
mock_core.HomeAssistant = MagicMock
mock_core.ServiceCall = MagicMock
mock_core.callback = lambda f: f
sys.modules["homeassistant.core"] = mock_core

mock_update_coord = ModuleType("homeassistant.helpers.update_coordinator")
class MockGenericCoord:
    def __class_getitem__(cls, item):
        return cls
mock_update_coord.DataUpdateCoordinator = MockGenericCoord
mock_update_coord.CoordinatorEntity = MockGenericCoord
sys.modules["homeassistant.helpers.update_coordinator"] = mock_update_coord

mock_restore = ModuleType("homeassistant.helpers.restore_state")
mock_restore.RestoreEntity = MagicMock
sys.modules["homeassistant.helpers.restore_state"] = mock_restore

mock_ent_plat = ModuleType("homeassistant.helpers.entity_platform")
mock_ent_plat.AddEntitiesCallback = MagicMock
sys.modules["homeassistant.helpers.entity_platform"] = mock_ent_plat

mock_cfg_val = ModuleType("homeassistant.helpers.config_validation")
mock_cfg_val.string = str
mock_cfg_val.boolean = bool
mock_cfg_val.ensure_list = list
sys.modules["homeassistant.helpers.config_validation"] = mock_cfg_val

# Add repo root to sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from custom_components.weekaqua.config_flow import (
    WeekAquaConfigFlow,
    format_and_validate_mac,
)
from custom_components.weekaqua.const import (
    CONF_MAC,
    CONF_NAME,
    CONF_MODEL_CODE,
    DOMAIN,
    MODEL_5745,
    MODEL_5746,
    MODEL_5747,
    MODEL_5749,
)


class MockRegistryEntry:
    def __init__(self, entity_id: str, unique_id: str, config_entry_id: str, disabled_by=None):
        self.entity_id = entity_id
        self.unique_id = unique_id
        self.config_entry_id = config_entry_id
        self.disabled_by = disabled_by


class MockDeviceEntry:
    def __init__(self, device_id: str, identifiers: set, connections: set, name: str, model: str):
        self.id = device_id
        self.identifiers = identifiers
        self.connections = connections
        self.name = name
        self.model = model


class TestWeekAquaReconfigure(unittest.TestCase):
    """Test WeekAqua Reconfigure Flow and Hardware Migration."""

    def setUp(self):
        """Set up mock environment."""
        self.entry_id = "test_entry_123"
        self.old_mac = "AA:BB:CC:11:22:33"
        self.new_mac = "DD:EE:FF:44:55:66"

        self.mock_entry = MagicMock()
        self.mock_entry.entry_id = self.entry_id
        self.mock_entry.unique_id = self.old_mac
        self.mock_entry.title = "WeekAqua M800 Pro"
        self.mock_entry.data = {
            CONF_MAC: self.old_mac,
            CONF_NAME: "WeekAqua M800 Pro",
            CONF_MODEL_CODE: MODEL_5745,
        }

        self.hass = MagicMock()
        self.hass.config_entries.async_get_entry.return_value = self.mock_entry
        self.hass.config_entries.async_entries.return_value = [self.mock_entry]

        # Setup Mock Entity Registry
        self.entities = {
            "light.weekaqua_light": MockRegistryEntry(
                "light.weekaqua_light", f"{self.old_mac}_light", self.entry_id
            ),
            "number.weekaqua_red": MockRegistryEntry(
                "number.weekaqua_red", f"{self.old_mac}_red", self.entry_id
            ),
            "number.weekaqua_white": MockRegistryEntry(
                "number.weekaqua_white", f"{self.old_mac}_white", self.entry_id,
                disabled_by="integration"
            ),
            "number.weekaqua_violet": MockRegistryEntry(
                "number.weekaqua_violet", f"{self.old_mac}_violet", self.entry_id,
                disabled_by="integration"
            ),
            "switch.weekaqua_schedule": MockRegistryEntry(
                "switch.weekaqua_schedule", f"{self.old_mac}_schedule_switch", self.entry_id
            ),
        }

        mock_er.async_get.return_value = mock_er
        mock_er.async_entries_for_config_entry.side_effect = (
            lambda ent_reg, e_id: [e for e in self.entities.values() if e.config_entry_id == e_id]
        )

        def mock_update_entity(entity_id, **kwargs):
            ent = self.entities.get(entity_id)
            if ent:
                if "new_unique_id" in kwargs:
                    ent.unique_id = kwargs["new_unique_id"]
                if "disabled_by" in kwargs:
                    ent.disabled_by = kwargs["disabled_by"]
            return ent

        mock_er.async_update_entity.side_effect = mock_update_entity

        # Setup Mock Device Registry
        self.mock_device = MockDeviceEntry(
            "dev_123",
            identifiers={(DOMAIN, self.old_mac)},
            connections={(mock_dr.CONNECTION_BLUETOOTH, self.old_mac)},
            name="WeekAqua M800 Pro",
            model="WeekAqua (5745)",
        )
        mock_dr.async_get.return_value = mock_dr
        mock_dr.async_get_device.side_effect = lambda identifiers: (
            self.mock_device if any(ident in self.mock_device.identifiers for ident in identifiers) else None
        )

        def mock_update_device(device_id, **kwargs):
            if "new_identifiers" in kwargs:
                self.mock_device.identifiers = kwargs["new_identifiers"]
            if "new_connections" in kwargs:
                self.mock_device.connections = kwargs["new_connections"]
            if "name" in kwargs:
                self.mock_device.name = kwargs["name"]
            if "model" in kwargs:
                self.mock_device.model = kwargs["model"]
            return self.mock_device

        mock_dr.async_update_device.side_effect = mock_update_device
        mock_bluetooth.async_discovered_service_info.return_value = []

    def test_mac_validation(self):
        """Test MAC address normalization and validation."""
        self.assertEqual(format_and_validate_mac("aa:bb:cc:11:22:33"), "AA:BB:CC:11:22:33")
        self.assertEqual(format_and_validate_mac("aabbcc112233"), "AA:BB:CC:11:22:33")
        self.assertEqual(format_and_validate_mac("AA-BB-CC-11-22-33"), "AA:BB:CC:11:22:33")
        self.assertEqual(format_and_validate_mac("aa.bb.cc.11.22.33"), "AA:BB:CC:11:22:33")
        self.assertIsNone(format_and_validate_mac("invalid_mac"))
        self.assertIsNone(format_and_validate_mac("ZZ:11:22:33:44:55"))

    def test_reconfigure_flow_mac_migration(self):
        """Test that MAC migration updates all entity unique_ids while preserving entity_ids."""
        flow = WeekAquaConfigFlow()
        flow.hass = self.hass
        flow.context = {"entry_id": self.entry_id}

        result = asyncio.run(flow.async_step_reconfigure(user_input={
            CONF_MAC: self.new_mac,
            CONF_NAME: "WeekAqua New Light",
            CONF_MODEL_CODE: MODEL_5745,
        }))

        self.assertEqual(result["type"], "abort")
        self.assertEqual(result["reason"], "reconfigure_successful")

        # Check that entity unique_ids were migrated
        self.assertEqual(self.entities["light.weekaqua_light"].unique_id, f"{self.new_mac}_light")
        self.assertEqual(self.entities["number.weekaqua_red"].unique_id, f"{self.new_mac}_red")
        self.assertEqual(self.entities["switch.weekaqua_schedule"].unique_id, f"{self.new_mac}_schedule_switch")

        # Check that device registry was updated
        self.assertIn((DOMAIN, self.new_mac), self.mock_device.identifiers)
        self.assertIn((mock_dr.CONNECTION_BLUETOOTH, self.new_mac), self.mock_device.connections)
        self.assertEqual(self.mock_device.name, "WeekAqua New Light")

    def test_reconfigure_flow_model_migration_rgb_to_rgbw(self):
        """Test model change from 4CH RGB/UV (5745) to RGBW (5747) enables White channel."""
        flow = WeekAquaConfigFlow()
        flow.hass = self.hass
        flow.context = {"entry_id": self.entry_id}

        # Initially white is disabled in 4CH
        self.assertIsNotNone(self.entities["number.weekaqua_white"].disabled_by)

        result = asyncio.run(flow.async_step_reconfigure(user_input={
            CONF_MAC: self.old_mac,
            CONF_NAME: "WeekAqua A/T Series",
            CONF_MODEL_CODE: MODEL_5747,  # Changed to RGBW model
        }))

        self.assertEqual(result["type"], "abort")
        self.assertEqual(result["reason"], "reconfigure_successful")

        # White channel should now be enabled (disabled_by is None)
        self.assertIsNone(self.entities["number.weekaqua_white"].disabled_by)
        # Device model should be updated
        self.assertEqual(self.mock_device.model, "WeekAqua (5747)")

    def test_reconfigure_flow_model_migration_to_6ch(self):
        """Test model change to 6CH Marine (5749) enables Violet channel."""
        flow = WeekAquaConfigFlow()
        flow.hass = self.hass
        flow.context = {"entry_id": self.entry_id}

        self.assertIsNotNone(self.entities["number.weekaqua_violet"].disabled_by)

        result = asyncio.run(flow.async_step_reconfigure(user_input={
            CONF_MAC: self.old_mac,
            CONF_NAME: "WeekAqua Marine",
            CONF_MODEL_CODE: MODEL_5749,
        }))

        self.assertEqual(result["type"], "abort")
        self.assertEqual(result["reason"], "reconfigure_successful")

        # Violet channel should now be enabled
        self.assertIsNone(self.entities["number.weekaqua_violet"].disabled_by)
        self.assertEqual(self.mock_device.model, "WeekAqua (5749)")

    def test_reconfigure_conflict_mac_abort(self):
        """Test that attempting to reconfigure to an already registered MAC aborts with already_configured."""
        other_entry = MagicMock()
        other_entry.entry_id = "other_entry_456"
        other_entry.unique_id = self.new_mac
        self.hass.config_entries.async_entries.return_value = [self.mock_entry, other_entry]

        flow = WeekAquaConfigFlow()
        flow.hass = self.hass
        flow.context = {"entry_id": self.entry_id}

        result = asyncio.run(flow.async_step_reconfigure(user_input={
            CONF_MAC: self.new_mac,
            CONF_NAME: "WeekAqua",
            CONF_MODEL_CODE: MODEL_5745,
        }))

        self.assertEqual(result["type"], "abort")
        self.assertEqual(result["reason"], "already_configured")


if __name__ == "__main__":
    unittest.main()
