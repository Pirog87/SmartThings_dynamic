"""Binary sensor platform for SmartThings Dynamic."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN
from .entity import EntityRef, SmartThingsDynamicBaseEntity
from .helpers import as_bool, bool_like, is_supported_meta_attribute, attribute_suffix

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator = runtime.coordinator

    added: set[str] = set()

    @callback
    def _async_discover() -> None:
        data = coordinator.data or {}
        devices: dict[str, Any] = data.get("devices") or {}
        statuses: dict[str, Any] = data.get("status") or {}

        new_entities: list[SmartThingsDynamicBinarySensor] = []

        for device_id, dev_status in statuses.items():
            device = devices.get(device_id)
            if not device:
                continue

            components = (dev_status.get("components") or {}) if isinstance(dev_status, dict) else {}
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
                        if value is None or not bool_like(value):
                            continue

                        if capability_id == "switch" and attr_name == "switch":
                            continue

                        key = f"{device_id}|{component_id}|{capability_id}|{attr_name}"
                        if key in added:
                            continue
                        added.add(key)

                        new_entities.append(
                            SmartThingsDynamicBinarySensor(
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
            _LOGGER.debug("Adding %d SmartThings Dynamic binary_sensor entities", len(new_entities))
            async_add_entities(new_entities)

    _async_discover()
    coordinator.async_add_listener(_async_discover)


class SmartThingsDynamicBinarySensor(SmartThingsDynamicBaseEntity, BinarySensorEntity):
    """Generic SmartThings attribute binary sensor."""

    @property
    def is_on(self) -> bool | None:
        return as_bool(self._attr_value())

    @property
    def device_class(self) -> BinarySensorDeviceClass | None:
        cap = (self.ref.capability_id or "").lower()
        attr = (self.ref.attribute or "").lower()

        if cap == "contactsensor" or attr == "contact":
            return BinarySensorDeviceClass.OPENING
        if "door" in attr:
            return BinarySensorDeviceClass.DOOR
        if "motion" in cap or "motion" in attr:
            return BinarySensorDeviceClass.MOTION
        if "smoke" in cap or "smoke" in attr:
            return BinarySensorDeviceClass.SMOKE
        if "water" in cap and ("leak" in attr or "wet" in attr):
            return BinarySensorDeviceClass.MOISTURE
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        payload = self._attr_payload() or {}
        attrs: dict[str, Any] = {
            "device_id": self.ref.device_id,
            "component": self.ref.component_id,
            "capability": self.ref.capability_id,
            "attribute": self.ref.attribute,
        }
        if "timestamp" in payload:
            attrs["timestamp"] = payload.get("timestamp")
        return attrs
