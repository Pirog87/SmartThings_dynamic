"""Entity base classes for SmartThings Dynamic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .helpers import component_label, device_label, get_capability_status


@dataclass(slots=True)
class EntityRef:
    device_id: str
    component_id: str
    capability_id: str
    attribute: str | None = None
    command: str | None = None


class SmartThingsDynamicBaseEntity(CoordinatorEntity):
    """Base entity that knows how to locate its device/component/capability in coordinator data."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator,
        *,
        entry_id: str,
        device: dict[str, Any],
        ref: EntityRef,
        name_suffix: str | None = None,
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._device = device
        self.ref = ref
        self._device_label = device_label(device)
        self._component_label = component_label(device, ref.component_id)
        self._name_suffix = name_suffix

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.ref.device_id)},
            name=self._device_label,
            manufacturer=self._device.get("manufacturerName") or self._device.get("manufacturer") or "SmartThings",
            model=self._device.get("modelName") or self._device.get("deviceTypeName") or None,
        )

    @property
    def unique_id(self) -> str:
        # Prefix with entry_id to avoid collisions if the same deviceId is linked by multiple entries.
        base = f"{self._entry_id}_{self.ref.device_id}_{self.ref.component_id}_{self.ref.capability_id}"
        if self.ref.attribute:
            base += f"_{self.ref.attribute}"
        if self.ref.command:
            base += f"_cmd_{self.ref.command}"
        return base

    @property
    def name(self) -> str:
        # device name is already represented by device registry; entity name should be concise
        parts = []
        if self.ref.component_id != "main":
            parts.append(self._component_label)
        if self._name_suffix:
            parts.append(self._name_suffix)
        return " · ".join(parts) if parts else self._device_label

    def _attr_payload(self) -> dict[str, Any] | None:
        if not self.ref.attribute:
            return None
        cap_status = get_capability_status(self.coordinator.data, self.ref.device_id, self.ref.component_id, self.ref.capability_id)
        payload = cap_status.get(self.ref.attribute)
        return payload if isinstance(payload, dict) else None

    def _attr_value(self) -> Any:
        payload = self._attr_payload()
        if payload is None:
            return None
        return payload.get("value")

    def _attr_unit(self) -> str | None:
        payload = self._attr_payload()
        if payload is None:
            return None
        unit = payload.get("unit")
        return str(unit) if unit is not None else None
