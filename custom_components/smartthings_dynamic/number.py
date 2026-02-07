"""Number platform for SmartThings Dynamic (numeric controls)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .api import SmartThingsApi
from .const import DOMAIN
from .entity import EntityRef, SmartThingsDynamicBaseEntity
from .helpers import capability_versions_for_component, get_capability_status

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator = runtime.coordinator
    api: SmartThingsApi = runtime.api

    added: set[str] = set()
    lock = asyncio.Lock()

    async def _async_discover() -> None:
        async with lock:
            data = coordinator.data or {}
            devices: dict[str, Any] = data.get("devices") or {}
            statuses: dict[str, Any] = data.get("status") or {}

            new_entities: list[SmartThingsDynamicNumber] = []

            for device_id, device in devices.items():
                dev_status = statuses.get(device_id) or {}
                comps_status = dev_status.get("components") or {}

                for comp_id, caps in _iter_component_capabilities(device):
                    if comp_id not in comps_status:
                        continue

                    for cap_id, version in caps.items():
                        cap_status = get_capability_status(data, device_id, comp_id, cap_id)
                        if not cap_status:
                            continue

                        try:
                            cap_def = await api.async_get_capability_definition(cap_id, version)
                        except Exception as err:  # noqa: BLE001
                            _LOGGER.debug("Could not fetch capability definition %s/%s: %s", cap_id, version, err)
                            continue

                        commands: dict[str, Any] = cap_def.get("commands") or {}

                        for cmd_name, cmd_def in commands.items():
                            args = (cmd_def or {}).get("arguments") or []
                            if len(args) != 1:
                                continue
                            arg = args[0]
                            arg_name = arg.get("name")
                            schema = (arg.get("schema") or {})
                            typ = schema.get("type")
                            if typ not in {"number", "integer"}:
                                continue
                            if not arg_name or arg_name not in cap_status:
                                continue

                            min_v, max_v, step = _constraints_from_schema(schema)

                            # Some Samsung capabilities publish settable* attributes in status; use them if present
                            min_v = _override_from_status(cap_status, f"settable{arg_name[0].upper()}{arg_name[1:]}Min", min_v)
                            max_v = _override_from_status(cap_status, f"settable{arg_name[0].upper()}{arg_name[1:]}Max", max_v)
                            step = _override_from_status(cap_status, f"settable{arg_name[0].upper()}{arg_name[1:]}Step", step)

                            # Skip if we don't have constraints - HA requires at least min or max
                            if min_v is None and max_v is None:
                                _LOGGER.debug(
                                    "Skipping number entity %s/%s/%s/%s - no min/max constraints",
                                    device_id, comp_id, cap_id, arg_name
                                )
                                continue

                            # Set reasonable defaults if only one bound is missing
                            if min_v is None:
                                min_v = 0.0
                            if max_v is None:
                                # Use a reasonable default based on current value
                                current_val = cap_status.get(arg_name, {}).get("value")
                                if isinstance(current_val, (int, float)):
                                    max_v = float(current_val) * 2 or 100.0
                                else:
                                    max_v = 100.0

                            key = f"{device_id}|{comp_id}|{cap_id}|{arg_name}|{cmd_name}"
                            if key in added:
                                continue
                            added.add(key)

                            cap_tail = cap_id.split(".")[-1]
                            suffix = f"{cap_tail}.{arg_name}"
                            new_entities.append(
                                SmartThingsDynamicNumber(
                                    coordinator,
                                    api,
                                    entry_id=entry.entry_id,
                                    device=device,
                                    ref=EntityRef(
                                        device_id=device_id,
                                        component_id=comp_id,
                                        capability_id=cap_id,
                                        attribute=str(arg_name),
                                    ),
                                    command=cmd_name,
                                    min_v=min_v,
                                    max_v=max_v,
                                    step=step,
                                    name_suffix=suffix,
                                )
                            )

            if new_entities:
                _LOGGER.debug("Adding %d SmartThings Dynamic number entities", len(new_entities))
                async_add_entities(new_entities)

    @callback
    def _async_schedule_discover() -> None:
        hass.async_create_task(_async_discover())

    _async_schedule_discover()
    coordinator.async_add_listener(_async_schedule_discover)


def _iter_component_capabilities(device: dict[str, Any]) -> list[tuple[str, dict[str, int]]]:
    result: list[tuple[str, dict[str, int]]] = []
    comps = device.get("components") or []
    if not comps:
        return [("main", {})]
    for comp in comps:
        cid = comp.get("id") or "main"
        result.append((cid, capability_versions_for_component(device, cid)))
    return result


def _constraints_from_schema(schema: dict[str, Any]) -> tuple[float | None, float | None, float | None]:
    min_v = schema.get("minimum")
    max_v = schema.get("maximum")
    step = schema.get("multipleOf")
    try:
        min_v = float(min_v) if min_v is not None else None
    except (TypeError, ValueError):
        min_v = None
    try:
        max_v = float(max_v) if max_v is not None else None
    except (TypeError, ValueError):
        max_v = None
    try:
        step = float(step) if step is not None else None
    except (TypeError, ValueError):
        step = None
    return min_v, max_v, step


def _override_from_status(cap_status: dict[str, Any], attr: str, fallback: float | None) -> float | None:
    payload = cap_status.get(attr)
    if isinstance(payload, dict):
        v = payload.get("value")
        if isinstance(v, (int, float)):
            return float(v)
    return fallback


class SmartThingsDynamicNumber(SmartThingsDynamicBaseEntity, NumberEntity):
    """Number entity mapped to a SmartThings command with a single numeric argument."""

    def __init__(
        self,
        coordinator,
        api: SmartThingsApi,
        *,
        entry_id: str,
        device: dict[str, Any],
        ref: EntityRef,
        command: str,
        min_v: float | None,
        max_v: float | None,
        step: float | None,
        name_suffix: str | None = None,
    ) -> None:
        super().__init__(coordinator, entry_id=entry_id, device=device, ref=ref, name_suffix=name_suffix)
        self._api = api
        self._command = command
        self._min_v = min_v
        self._max_v = max_v
        self._step = step

    @property
    def native_value(self) -> float | None:
        val = self._attr_value()
        if isinstance(val, (int, float)):
            return float(val)
        return None

    @property
    def native_min_value(self) -> float:
        return self._min_v if self._min_v is not None else 0.0

    @property
    def native_max_value(self) -> float:
        return self._max_v if self._max_v is not None else 100.0

    @property
    def native_step(self) -> float | None:
        return self._step

    async def async_set_native_value(self, value: float) -> None:
        await self._api.async_execute_command(
            self.ref.device_id,
            self.ref.component_id,
            self.ref.capability_id,
            self._command,
            [value],
        )
        await self.coordinator.async_request_refresh()