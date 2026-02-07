"""Helpers for SmartThings Dynamic entity discovery."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


def device_label(device: dict[str, Any]) -> str:
    return (
        device.get("label")
        or device.get("name")
        or device.get("deviceLabel")
        or device.get("deviceTypeName")
        or device.get("deviceId", "SmartThings Device")
    )


def component_label(device: dict[str, Any], component_id: str) -> str:
    for comp in device.get("components", []) or []:
        if comp.get("id") == component_id:
            return comp.get("label") or comp.get("id") or component_id
    return component_id


def capability_tail(capability_id: str) -> str:
    """Return the last segment of a capability id (after the final dot)."""
    return str(capability_id).split(".")[-1]


def attribute_suffix(capability_id: str, attribute: str) -> str:
    """Build a concise, stable suffix for an entity name from capability+attribute."""
    cap = capability_tail(capability_id)
    attr = str(attribute)
    if attr.lower() == cap.lower():
        return cap
    return f"{cap}.{attr}"


def iter_device_components(data: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any], str]]:
    """Yield (device_id, device_obj, component_id)."""
    devices: dict[str, Any] = data.get("devices") or {}
    for device_id, dev in devices.items():
        comps = dev.get("components") or []
        if not comps:
            yield device_id, dev, "main"
            continue
        for comp in comps:
            cid = comp.get("id") or "main"
            yield device_id, dev, cid


def capability_versions_for_component(device: dict[str, Any], component_id: str) -> dict[str, int]:
    """Map capability_id -> version for a given component."""
    for comp in device.get("components", []) or []:
        if (comp.get("id") or "main") != component_id:
            continue
        result: dict[str, int] = {}
        for cap in comp.get("capabilities", []) or []:
            cap_id = cap.get("id")
            ver = cap.get("version", 1)
            if cap_id:
                result[str(cap_id)] = int(ver)
        return result
    return {}


def get_capability_status(data: dict[str, Any], device_id: str, component_id: str, capability_id: str) -> dict[str, Any]:
    """Return status dict for a capability (attribute_name -> {value, unit, ...})."""
    status_all: dict[str, Any] = data.get("status") or {}
    dev_status = status_all.get(device_id)
    
    # --- FIX: SECURITY CHECK ---
    # Ensure dev_status is a dict before accessing .get()
    if not isinstance(dev_status, dict):
        return {}
        
    comps: dict[str, Any] = dev_status.get("components") or {}
    comp_status: dict[str, Any] = comps.get(component_id) or {}
    cap_status: dict[str, Any] = comp_status.get(capability_id) or {}
    if isinstance(cap_status, dict):
        return cap_status
    return {}


def iter_capability_attributes(cap_status: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    for attr, payload in (cap_status or {}).items():
        if not isinstance(payload, dict):
            continue
        yield attr, payload


def safe_state(value: Any) -> str | int | float | None:
    """Convert arbitrary SmartThings values to a HA-friendly scalar state."""
    if value is None:
        return None
    
    if isinstance(value, str):
        value_lower = value.lower().strip()
        if value_lower in ('none', 'null', 'n/a', 'na', 'unknown', ''):
            return None
        return value
    
    if isinstance(value, (int, float)):
        return value
    
    if isinstance(value, bool):
        return "on" if value else "off"
    
    try:
        s = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except TypeError:
        return str(value)

    if len(s) <= 255:
        return s
    
    if isinstance(value, list):
        return f"list[{len(value)}]"
    if isinstance(value, dict):
        return f"dict[{len(value)}]"
    return "complex"


def is_supported_meta_attribute(attr_name: str) -> bool:
    """Attributes that are usually only metadata."""
    lower = attr_name.lower()
    return (
        lower.startswith("supported")
        or lower.endswith("range")
        or lower.endswith("ranges")
        or lower in {"supportedoptions", "referencetable", "settable", "supportedcommands"}
    )


def bool_like(value: Any) -> bool:
    if isinstance(value, bool):
        return True
    if isinstance(value, str) and value.lower() in {"on", "off", "open", "closed", "true", "false"}:
        return True
    return False


def as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        v = value.lower()
        if v in {"on", "open", "true"}:
            return True
        if v in {"off", "closed", "false"}:
            return False
    return None