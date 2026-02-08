"""Shared fixtures and HomeAssistant module mocking for SmartThings Dynamic tests.

Since we cannot install the full homeassistant package in a lightweight test
environment, we stub just enough of the HA API surface so that our integration
modules can be imported and their pure-logic functions tested.
"""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Mock homeassistant modules BEFORE any custom_components imports
# ---------------------------------------------------------------------------

_HA_MODULES: list[str] = [
    "homeassistant",
    "homeassistant.config_entries",
    "homeassistant.core",
    "homeassistant.exceptions",
    "homeassistant.helpers",
    "homeassistant.helpers.config_entry_oauth2_flow",
    "homeassistant.helpers.typing",
    "homeassistant.helpers.config_validation",
    "homeassistant.helpers.entity",
    "homeassistant.helpers.update_coordinator",
    "homeassistant.helpers.aiohttp_client",
    "homeassistant.components",
    "homeassistant.components.sensor",
    "homeassistant.components.binary_sensor",
    "homeassistant.components.switch",
    "homeassistant.components.button",
    "homeassistant.components.select",
    "homeassistant.components.number",
    "homeassistant.components.camera",
    "homeassistant.components.vacuum",
    "homeassistant.components.application_credentials",
    "homeassistant.util",
    "homeassistant.util.dt",
]


def _install_ha_mocks() -> None:
    """Register mock modules so that ``import homeassistant...`` succeeds."""
    for name in _HA_MODULES:
        if name not in sys.modules:
            mod = ModuleType(name)
            mod.__dict__.setdefault("__all__", [])
            sys.modules[name] = mod

    # --- homeassistant.core ---
    ha_core = sys.modules["homeassistant.core"]
    ha_core.HomeAssistant = MagicMock  # type: ignore[attr-defined]
    ha_core.ServiceCall = MagicMock  # type: ignore[attr-defined]
    ha_core.callback = lambda fn: fn  # type: ignore[attr-defined]

    # --- homeassistant.config_entries ---
    ha_ce = sys.modules["homeassistant.config_entries"]
    ha_ce.ConfigEntry = MagicMock  # type: ignore[attr-defined]

    # --- homeassistant.exceptions ---
    ha_exc = sys.modules["homeassistant.exceptions"]

    class _HomeAssistantError(Exception):
        pass

    class _ConfigEntryAuthFailed(Exception):
        pass

    ha_exc.HomeAssistantError = _HomeAssistantError  # type: ignore[attr-defined]
    ha_exc.ConfigEntryAuthFailed = _ConfigEntryAuthFailed  # type: ignore[attr-defined]

    # --- homeassistant.helpers.config_entry_oauth2_flow ---
    oauth_mod = sys.modules["homeassistant.helpers.config_entry_oauth2_flow"]
    oauth_mod.OAuth2Session = MagicMock  # type: ignore[attr-defined]
    oauth_mod.AbstractOAuth2FlowHandler = type("AbstractOAuth2FlowHandler", (), {})  # type: ignore[attr-defined]
    oauth_mod.async_get_config_entry_implementation = MagicMock  # type: ignore[attr-defined]

    # --- homeassistant.helpers.config_validation ---
    cv_mod = sys.modules["homeassistant.helpers.config_validation"]
    cv_mod.string = str  # type: ignore[attr-defined]

    # --- homeassistant.helpers.typing ---
    typing_mod = sys.modules["homeassistant.helpers.typing"]
    typing_mod.ConfigType = dict  # type: ignore[attr-defined]

    # --- homeassistant.helpers.entity ---
    entity_mod = sys.modules["homeassistant.helpers.entity"]
    entity_mod.DeviceInfo = dict  # type: ignore[attr-defined]

    # --- homeassistant.helpers.update_coordinator ---
    uc_mod = sys.modules["homeassistant.helpers.update_coordinator"]

    class _DataUpdateCoordinator:
        def __init_subclass__(cls, **kw):
            super().__init_subclass__(**kw)

        def __class_getitem__(cls, item):
            return cls

        def __init__(self, *a, **kw):
            self.data = {}
            self.update_interval = kw.get("update_interval")

    class _CoordinatorEntity:
        def __init__(self, coordinator, *a, **kw):
            self.coordinator = coordinator

    class _UpdateFailed(Exception):
        pass

    uc_mod.DataUpdateCoordinator = _DataUpdateCoordinator  # type: ignore[attr-defined]
    uc_mod.CoordinatorEntity = _CoordinatorEntity  # type: ignore[attr-defined]
    uc_mod.UpdateFailed = _UpdateFailed  # type: ignore[attr-defined]

    # --- homeassistant.helpers.aiohttp_client ---
    aiohttp_mod = sys.modules["homeassistant.helpers.aiohttp_client"]
    aiohttp_mod.async_get_clientsession = MagicMock  # type: ignore[attr-defined]

    # --- homeassistant.components.sensor ---
    sensor_mod = sys.modules["homeassistant.components.sensor"]
    sensor_mod.SensorEntity = type("SensorEntity", (_CoordinatorEntity,), {})  # type: ignore[attr-defined]
    sensor_mod.SensorDeviceClass = MagicMock()  # type: ignore[attr-defined]
    sensor_mod.SensorStateClass = MagicMock()  # type: ignore[attr-defined]

    # --- homeassistant.components.binary_sensor ---
    bs_mod = sys.modules["homeassistant.components.binary_sensor"]
    bs_mod.BinarySensorEntity = type("BinarySensorEntity", (_CoordinatorEntity,), {})  # type: ignore[attr-defined]
    bs_mod.BinarySensorDeviceClass = MagicMock()  # type: ignore[attr-defined]

    # --- homeassistant.components.switch ---
    sw_mod = sys.modules["homeassistant.components.switch"]
    sw_mod.SwitchEntity = type("SwitchEntity", (_CoordinatorEntity,), {})  # type: ignore[attr-defined]

    # --- homeassistant.components.button ---
    btn_mod = sys.modules["homeassistant.components.button"]
    btn_mod.ButtonEntity = type("ButtonEntity", (_CoordinatorEntity,), {})  # type: ignore[attr-defined]

    # --- homeassistant.components.select ---
    sel_mod = sys.modules["homeassistant.components.select"]
    sel_mod.SelectEntity = type("SelectEntity", (_CoordinatorEntity,), {})  # type: ignore[attr-defined]

    # --- homeassistant.components.number ---
    num_mod = sys.modules["homeassistant.components.number"]
    num_mod.NumberEntity = type("NumberEntity", (_CoordinatorEntity,), {})  # type: ignore[attr-defined]

    # --- homeassistant.components.camera ---
    cam_mod = sys.modules["homeassistant.components.camera"]
    cam_mod.Camera = type("Camera", (_CoordinatorEntity,), {})  # type: ignore[attr-defined]

    # --- homeassistant.components.vacuum ---
    vac_mod = sys.modules["homeassistant.components.vacuum"]
    vac_mod.StateVacuumEntity = type("StateVacuumEntity", (_CoordinatorEntity,), {})  # type: ignore[attr-defined]
    vac_mod.VacuumEntityFeature = MagicMock()  # type: ignore[attr-defined]
    vac_mod.VacuumActivity = MagicMock()  # type: ignore[attr-defined]

    # --- homeassistant.components.application_credentials ---
    ac_mod = sys.modules["homeassistant.components.application_credentials"]
    ac_mod.AuthImplementation = type("AuthImplementation", (), {})  # type: ignore[attr-defined]
    ac_mod.AuthorizationServer = MagicMock  # type: ignore[attr-defined]
    ac_mod.ClientCredential = MagicMock  # type: ignore[attr-defined]

    # --- homeassistant (root) ---
    ha_root = sys.modules["homeassistant"]
    ha_root.config_entries = sys.modules["homeassistant.config_entries"]  # type: ignore[attr-defined]
    ha_root.core = ha_core  # type: ignore[attr-defined]

    # Ensure helpers sub-modules are accessible as attributes
    ha_helpers = sys.modules["homeassistant.helpers"]
    ha_helpers.config_entry_oauth2_flow = oauth_mod  # type: ignore[attr-defined]
    ha_helpers.config_validation = cv_mod  # type: ignore[attr-defined]
    ha_helpers.entity = entity_mod  # type: ignore[attr-defined]
    ha_helpers.update_coordinator = uc_mod  # type: ignore[attr-defined]
    ha_helpers.aiohttp_client = aiohttp_mod  # type: ignore[attr-defined]

    ha_util = sys.modules["homeassistant.util"]
    ha_util.dt = sys.modules["homeassistant.util.dt"]  # type: ignore[attr-defined]


# Install mocks at conftest import time (before test collection)
_install_ha_mocks()


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_device() -> dict:
    """A realistic SmartThings device dict."""
    return {
        "deviceId": "device-001",
        "label": "Samsung Washer",
        "name": "Washer",
        "manufacturerName": "Samsung",
        "modelName": "WF45R6100AW",
        "components": [
            {
                "id": "main",
                "label": "Main",
                "capabilities": [
                    {"id": "switch", "version": 1},
                    {"id": "washerOperatingState", "version": 1},
                    {"id": "custom.washerWaterTemperature", "version": 1},
                ],
            },
            {
                "id": "sub",
                "label": "AddWash Door",
                "capabilities": [
                    {"id": "contactSensor", "version": 1},
                ],
            },
        ],
    }


@pytest.fixture
def sample_device_no_label() -> dict:
    """A device with no label field."""
    return {
        "deviceId": "device-002",
        "name": "Kitchen Fridge",
        "components": [{"id": "main", "capabilities": []}],
    }


@pytest.fixture
def sample_coordinator_data(sample_device: dict) -> dict:
    """Coordinator data with devices and status."""
    return {
        "devices": {
            "device-001": sample_device,
        },
        "status": {
            "device-001": {
                "components": {
                    "main": {
                        "switch": {
                            "switch": {"value": "on"},
                        },
                        "washerOperatingState": {
                            "machineState": {"value": "running"},
                            "washerJobState": {"value": "washing"},
                        },
                    },
                    "sub": {
                        "contactSensor": {
                            "contact": {"value": "closed"},
                        },
                    },
                },
            },
        },
    }
