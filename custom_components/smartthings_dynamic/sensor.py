"""Sensor platform for SmartThings Dynamic."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util

from .const import (
    CONF_EXPOSE_RAW_SENSORS,
    DOMAIN,
    ENERGY_SUB_ATTRIBUTES,
    ENERGY_UNIT_MAP,
)
from .entity import EntityRef, SmartThingsDynamicBaseEntity
from .helpers import attribute_suffix, bool_like, is_supported_meta_attribute, safe_state

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator = runtime.coordinator

    expose_raw = bool(entry.options.get(CONF_EXPOSE_RAW_SENSORS, False))

    added: set[str] = set()

    @callback
    def _async_discover() -> None:
        data = coordinator.data or {}
        devices: dict[str, Any] = data.get("devices") or {}
        statuses: dict[str, Any] = data.get("status") or {}

        new_entities: list[SmartThingsDynamicSensor] = []

        for device_id, dev_status in statuses.items():
            device = devices.get(device_id)
            if not device:
                continue

            # --- FIX: ZABEZPIECZENIE PRZED BŁĘDNYM FORMATEM DANYCH ---
            # Jeśli dev_status jest stringiem (np. błąd API) lub None, pomijamy
            if not isinstance(dev_status, dict):
                continue
            # ---------------------------------------------------------

            components = dev_status.get("components") or {}
            if not isinstance(components, dict):
                continue

            for component_id, comp_status in components.items():
                if not isinstance(comp_status, dict):
                    continue
                for capability_id, cap_status in comp_status.items():
                    if not isinstance(cap_status, dict):
                        continue
                    for attr_name, payload in cap_status.items():
                        if not isinstance(payload, dict):
                            continue
                        if is_supported_meta_attribute(attr_name):
                            continue

                        value = payload.get("value")
                        if value is None:
                            continue

                        # --- COMPLEX ATTRIBUTE HANDLING (JSON) ---
                        if isinstance(value, dict):
                            interesting_subkeys = [
                                "completionTime", "remainingTime",
                                "movenOvenState", "processState", "meatProbeTemperature",
                                *ENERGY_SUB_ATTRIBUTES,
                            ]

                            for sub_key in interesting_subkeys:
                                if sub_key in value and value[sub_key] is not None:
                                    sub_key_id = f"{attr_name}.{sub_key}"
                                    key = f"{device_id}|{component_id}|{capability_id}|{sub_key_id}"

                                    if key in added:
                                        continue
                                    added.add(key)

                                    new_entities.append(
                                        SmartThingsDynamicSensor(
                                            coordinator,
                                            entry_id=entry.entry_id,
                                            device=device,
                                            ref=EntityRef(
                                                device_id=device_id,
                                                component_id=component_id,
                                                capability_id=capability_id,
                                                attribute=attr_name,
                                            ),
                                            sub_attribute=sub_key,
                                            name_suffix=attribute_suffix(capability_id, sub_key_id),
                                        )
                                    )

                            if not expose_raw:
                                continue

                        # --- STANDARD SENSORS ---
                        if isinstance(value, str) and value.lower() in ('none', 'null', 'n/a'):
                            continue

                        if bool_like(value):
                            continue

                        if capability_id == "switch" and attr_name == "switch":
                            continue

                        key = f"{device_id}|{component_id}|{capability_id}|{attr_name}"
                        if key in added:
                            continue
                        added.add(key)

                        new_entities.append(
                            SmartThingsDynamicSensor(
                                coordinator,
                                entry_id=entry.entry_id,
                                device=device,
                                ref=EntityRef(
                                    device_id=device_id,
                                    component_id=component_id,
                                    capability_id=capability_id,
                                    attribute=attr_name,
                                ),
                                name_suffix=attribute_suffix(capability_id, attr_name),
                            )
                        )

        if new_entities:
            _LOGGER.debug("Adding %d SmartThings Dynamic sensor entities", len(new_entities))
            async_add_entities(new_entities)

    _async_discover()
    coordinator.async_add_listener(_async_discover)


class SmartThingsDynamicSensor(SmartThingsDynamicBaseEntity, SensorEntity):
    """Generic SmartThings attribute sensor."""

    def __init__(
        self,
        coordinator,
        *,
        entry_id: str,
        device: dict[str, Any],
        ref: EntityRef,
        name_suffix: str | None = None,
        sub_attribute: str | None = None,
    ) -> None:
        super().__init__(coordinator, entry_id=entry_id, device=device, ref=ref, name_suffix=name_suffix)
        self._sub_attribute = sub_attribute

    @property
    def native_value(self):
        val = self._attr_value()

        if self._sub_attribute:
            if isinstance(val, dict):
                val = val.get(self._sub_attribute)
            else:
                return None

        if isinstance(val, str) and val.lower() in ('none', 'null', 'n/a'):
            return None

        # Check for ISO8601 Timestamps
        if isinstance(val, str) and "T" in val and val.endswith("Z"):
            try:
                parsed_dt = dt_util.parse_datetime(val)
                if parsed_dt is not None:
                    return parsed_dt
            except (ValueError, TypeError):
                pass

        return safe_state(val)

    # -----------------------------------------------------------------
    # Helpers for energy-aware classification
    # -----------------------------------------------------------------

    def _effective_attr(self) -> str:
        """Lower-cased attribute (or sub-attribute) name used for classification."""
        return (self._sub_attribute or self.ref.attribute or "").lower()

    def _is_energy_capability(self) -> bool:
        """True when the parent capability is an energy/power reporting one."""
        cap = (self.ref.capability_id or "").lower()
        return any(
            k in cap
            for k in ("powerconsumption", "powermeter", "energymeter", "powerusage", "energyusage")
        )

    # -----------------------------------------------------------------
    # Core HA sensor properties
    # -----------------------------------------------------------------

    @property
    def native_unit_of_measurement(self) -> str | None:
        if self.device_class == SensorDeviceClass.TIMESTAMP:
            return None

        # 1. Explicit unit from SmartThings payload
        unit = self._attr_unit()
        if unit is not None:
            if unit == "C":
                return "°C"
            if unit == "F":
                return "°F"
            if unit == "K":
                return "K"
            # Normalise energy-related units
            normalised = ENERGY_UNIT_MAP.get(unit)
            if normalised:
                return normalised
            return unit

        # 2. Infer unit from attribute name / device class
        attr = self._effective_attr()
        dc = self.device_class

        if dc == SensorDeviceClass.POWER:
            return "W"
        if dc == SensorDeviceClass.ENERGY:
            return "Wh"
        if dc == SensorDeviceClass.VOLTAGE:
            return "V"
        if dc == SensorDeviceClass.CURRENT:
            return "A"

        val = self.native_value
        if (
            isinstance(val, (int, float))
            and 0 <= float(val) <= 100
            and ("progress" in attr or "percentage" in attr or attr.endswith("usage"))
        ):
            return "%"

        return None

    @property
    def device_class(self) -> SensorDeviceClass | None:
        attr = self._effective_attr()

        # Timestamps
        if isinstance(self.native_value, datetime):
            return SensorDeviceClass.TIMESTAMP
        if "time" in attr and ("completion" in attr or "end" in attr):
            return SensorDeviceClass.TIMESTAMP

        # Battery
        if attr == "battery":
            return SensorDeviceClass.BATTERY

        # Temperature
        if (
            attr in {"temperature", "measuredtemperature", "oventemperature", "meatprobetemperature"}
            or attr.endswith("temperature")
        ):
            return SensorDeviceClass.TEMPERATURE

        # Humidity
        if attr.endswith("humidity"):
            return SensorDeviceClass.HUMIDITY

        # --- Energy / Power ---
        if attr in {"power", "deltaenergy"} or attr.endswith("power"):
            return SensorDeviceClass.POWER
        if attr in {"energy", "powerenergy", "totalenergy"} or attr.endswith("energy"):
            return SensorDeviceClass.ENERGY
        if "voltage" in attr:
            return SensorDeviceClass.VOLTAGE
        if attr in {"current", "amperage"} or "current" in attr and "state" not in attr:
            return SensorDeviceClass.CURRENT
        if "powerfactor" in attr or "power_factor" in attr:
            return SensorDeviceClass.POWER_FACTOR
        if attr == "frequency" or attr.endswith("frequency"):
            return SensorDeviceClass.FREQUENCY

        return None

    @property
    def state_class(self) -> SensorStateClass | None:
        """Return the state class so HA records long-term statistics."""
        dc = self.device_class
        if dc is None:
            return None

        attr = self._effective_attr()

        # Cumulative energy values → TOTAL_INCREASING
        if dc == SensorDeviceClass.ENERGY:
            # deltaEnergy is a differential, not cumulative
            if "delta" in attr:
                return SensorStateClass.MEASUREMENT
            return SensorStateClass.TOTAL_INCREASING

        # Instantaneous measurements
        if dc in {
            SensorDeviceClass.POWER,
            SensorDeviceClass.VOLTAGE,
            SensorDeviceClass.CURRENT,
            SensorDeviceClass.POWER_FACTOR,
            SensorDeviceClass.FREQUENCY,
            SensorDeviceClass.TEMPERATURE,
            SensorDeviceClass.HUMIDITY,
            SensorDeviceClass.BATTERY,
        }:
            return SensorStateClass.MEASUREMENT

        return None

    @property
    def suggested_display_precision(self) -> int | None:
        dc = self.device_class
        if dc == SensorDeviceClass.ENERGY:
            return 2
        if dc == SensorDeviceClass.POWER:
            return 1
        if dc == SensorDeviceClass.VOLTAGE:
            return 1
        if dc == SensorDeviceClass.CURRENT:
            return 2
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        base_payload = self._attr_payload() or {}

        if self._sub_attribute:
            return {
                "parent_attribute": self.ref.attribute,
                "key": self._sub_attribute
            }

        attrs: dict[str, Any] = {
            "device_id": self.ref.device_id,
            "component": self.ref.component_id,
            "capability": self.ref.capability_id,
            "attribute": self.ref.attribute,
        }

        if "timestamp" in base_payload:
            attrs["timestamp"] = base_payload.get("timestamp")
        if "unit" in base_payload:
            attrs["unit"] = base_payload.get("unit")

        val = base_payload.get("value")
        if isinstance(val, dict):
            for k, v in val.items():
                if isinstance(v, (str, int, float, bool)) and len(str(v)) < 100:
                    attrs[k] = v

        return attrs
