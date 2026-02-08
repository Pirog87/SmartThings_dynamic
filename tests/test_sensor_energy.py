"""Tests for energy monitoring in the sensor platform."""

from __future__ import annotations

from unittest.mock import MagicMock

# Import mocked HA classes so we can reference device/state class enums
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

from custom_components.smartthings_dynamic.entity import EntityRef
from custom_components.smartthings_dynamic.sensor import SmartThingsDynamicSensor

# ─── Helpers ────────────────────────────────────────────────────────────────


def _make_sensor(
    capability_id: str = "powerMeter",
    attribute: str = "power",
    sub_attribute: str | None = None,
    value=150.5,
    unit: str | None = None,
) -> SmartThingsDynamicSensor:
    """Create a sensor backed by a fake coordinator with the given data."""
    ref = EntityRef(
        device_id="dev-1",
        component_id="main",
        capability_id=capability_id,
        attribute=attribute,
    )

    payload: dict = {"value": value}
    if unit is not None:
        payload["unit"] = unit

    coordinator = MagicMock()
    coordinator.data = {
        "devices": {
            "dev-1": {
                "deviceId": "dev-1",
                "label": "Test Device",
                "components": [{"id": "main", "capabilities": []}],
            }
        },
        "status": {
            "dev-1": {
                "components": {
                    "main": {
                        capability_id: {
                            attribute: payload,
                        }
                    }
                }
            }
        },
    }

    device = coordinator.data["devices"]["dev-1"]
    sensor = SmartThingsDynamicSensor(
        coordinator,
        entry_id="test-entry",
        device=device,
        ref=ref,
        sub_attribute=sub_attribute,
        name_suffix=f"{capability_id}.{sub_attribute or attribute}",
    )
    return sensor


# ─── device_class ───────────────────────────────────────────────────────────


class TestEnergyDeviceClass:
    def test_power_attribute(self):
        s = _make_sensor(attribute="power", value=100)
        assert s.device_class == SensorDeviceClass.POWER

    def test_energy_attribute(self):
        s = _make_sensor(attribute="energy", value=1234.5)
        assert s.device_class == SensorDeviceClass.ENERGY

    def test_attr_ending_with_power(self):
        s = _make_sensor(attribute="activePower", value=50)
        assert s.device_class == SensorDeviceClass.POWER

    def test_attr_ending_with_energy(self):
        s = _make_sensor(attribute="totalEnergy", value=999)
        assert s.device_class == SensorDeviceClass.ENERGY

    def test_delta_energy_is_power(self):
        s = _make_sensor(
            capability_id="powerConsumption",
            attribute="powerConsumption",
            sub_attribute="deltaEnergy",
            value={"deltaEnergy": 0.5, "energy": 100, "power": 150},
        )
        assert s.device_class == SensorDeviceClass.POWER

    def test_power_energy_sub_attr_is_energy(self):
        s = _make_sensor(
            capability_id="powerConsumption",
            attribute="powerConsumption",
            sub_attribute="powerEnergy",
            value={"powerEnergy": 0.05, "energy": 100, "power": 150},
        )
        assert s.device_class == SensorDeviceClass.ENERGY

    def test_voltage_attribute(self):
        s = _make_sensor(attribute="voltage", value=230)
        assert s.device_class == SensorDeviceClass.VOLTAGE

    def test_amperage_attribute(self):
        s = _make_sensor(attribute="amperage", value=5.2)
        assert s.device_class == SensorDeviceClass.CURRENT

    def test_current_attribute(self):
        s = _make_sensor(attribute="current", value=3.1)
        assert s.device_class == SensorDeviceClass.CURRENT

    def test_power_factor_attribute(self):
        s = _make_sensor(attribute="powerFactor", value=0.95)
        assert s.device_class == SensorDeviceClass.POWER_FACTOR

    def test_frequency_attribute(self):
        s = _make_sensor(attribute="frequency", value=50)
        assert s.device_class == SensorDeviceClass.FREQUENCY

    def test_non_energy_returns_none(self):
        s = _make_sensor(
            capability_id="washerOperatingState",
            attribute="machineState",
            value="running",
        )
        assert s.device_class is None


# ─── state_class ────────────────────────────────────────────────────────────


class TestEnergyStateClass:
    def test_power_is_measurement(self):
        s = _make_sensor(attribute="power", value=150)
        assert s.state_class == SensorStateClass.MEASUREMENT

    def test_energy_is_total_increasing(self):
        s = _make_sensor(attribute="energy", value=1234.5)
        assert s.state_class == SensorStateClass.TOTAL_INCREASING

    def test_delta_energy_is_measurement(self):
        """deltaEnergy is a differential, not cumulative."""
        s = _make_sensor(
            capability_id="powerConsumption",
            attribute="powerConsumption",
            sub_attribute="deltaEnergy",
            value={"deltaEnergy": 0.5, "energy": 100, "power": 150},
        )
        assert s.state_class == SensorStateClass.MEASUREMENT

    def test_total_energy_is_total_increasing(self):
        s = _make_sensor(attribute="totalEnergy", value=5000)
        assert s.state_class == SensorStateClass.TOTAL_INCREASING

    def test_voltage_is_measurement(self):
        s = _make_sensor(attribute="voltage", value=230)
        assert s.state_class == SensorStateClass.MEASUREMENT

    def test_temperature_is_measurement(self):
        s = _make_sensor(attribute="temperature", value=22.5)
        assert s.state_class == SensorStateClass.MEASUREMENT

    def test_battery_is_measurement(self):
        s = _make_sensor(attribute="battery", value=85)
        assert s.state_class == SensorStateClass.MEASUREMENT

    def test_non_energy_no_state_class(self):
        s = _make_sensor(
            capability_id="washerOperatingState",
            attribute="machineState",
            value="running",
        )
        assert s.state_class is None


# ─── native_unit_of_measurement ─────────────────────────────────────────────


class TestEnergyUnits:
    def test_power_inferred_unit(self):
        s = _make_sensor(attribute="power", value=150)
        assert s.native_unit_of_measurement == "W"

    def test_energy_inferred_unit(self):
        s = _make_sensor(attribute="energy", value=1234.5)
        assert s.native_unit_of_measurement == "Wh"

    def test_voltage_inferred_unit(self):
        s = _make_sensor(attribute="voltage", value=230)
        assert s.native_unit_of_measurement == "V"

    def test_current_inferred_unit(self):
        s = _make_sensor(attribute="current", value=5)
        assert s.native_unit_of_measurement == "A"

    def test_explicit_kw_unit_normalised(self):
        s = _make_sensor(attribute="power", value=1.5, unit="kW")
        assert s.native_unit_of_measurement == "kW"

    def test_explicit_kwh_unit_normalised(self):
        s = _make_sensor(attribute="energy", value=100, unit="kWh")
        assert s.native_unit_of_measurement == "kWh"

    def test_explicit_watts_long_form(self):
        s = _make_sensor(attribute="power", value=100, unit="Watts")
        assert s.native_unit_of_measurement == "W"

    def test_celsius_still_works(self):
        s = _make_sensor(attribute="temperature", value=22, unit="C")
        assert s.native_unit_of_measurement == "°C"


# ─── suggested_display_precision ────────────────────────────────────────────


class TestDisplayPrecision:
    def test_energy_precision(self):
        s = _make_sensor(attribute="energy", value=1234.567)
        assert s.suggested_display_precision == 2

    def test_power_precision(self):
        s = _make_sensor(attribute="power", value=150.123)
        assert s.suggested_display_precision == 1

    def test_voltage_precision(self):
        s = _make_sensor(attribute="voltage", value=230.5)
        assert s.suggested_display_precision == 1

    def test_current_precision(self):
        s = _make_sensor(attribute="current", value=5.123)
        assert s.suggested_display_precision == 2

    def test_non_energy_no_precision(self):
        s = _make_sensor(
            capability_id="washerOperatingState",
            attribute="machineState",
            value="running",
        )
        assert s.suggested_display_precision is None


# ─── powerConsumption sub-attribute extraction ──────────────────────────────


class TestPowerConsumptionSubAttributes:
    """Verify that complex powerConsumption dicts produce proper sub-sensors."""

    def test_energy_sub_attr_device_class(self):
        s = _make_sensor(
            capability_id="powerConsumption",
            attribute="powerConsumption",
            sub_attribute="energy",
            value={"energy": 1234.5, "power": 150, "deltaEnergy": 0.5},
        )
        assert s.device_class == SensorDeviceClass.ENERGY
        assert s.state_class == SensorStateClass.TOTAL_INCREASING

    def test_power_sub_attr_device_class(self):
        s = _make_sensor(
            capability_id="powerConsumption",
            attribute="powerConsumption",
            sub_attribute="power",
            value={"energy": 1234.5, "power": 150, "deltaEnergy": 0.5},
        )
        assert s.device_class == SensorDeviceClass.POWER
        assert s.state_class == SensorStateClass.MEASUREMENT

    def test_sub_attr_native_value(self):
        s = _make_sensor(
            capability_id="powerConsumption",
            attribute="powerConsumption",
            sub_attribute="power",
            value={"energy": 1234.5, "power": 150, "deltaEnergy": 0.5},
        )
        assert s.native_value == 150

    def test_sub_attr_energy_native_value(self):
        s = _make_sensor(
            capability_id="powerConsumption",
            attribute="powerConsumption",
            sub_attribute="energy",
            value={"energy": 1234.5, "power": 150, "deltaEnergy": 0.5},
        )
        assert s.native_value == 1234.5
