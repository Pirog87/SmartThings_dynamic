"""Switch platform for SmartThings Dynamic."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .api import SmartThingsApi
from .const import DOMAIN
from .entity import EntityRef, SmartThingsDynamicBaseEntity
from .helpers import as_bool, capability_versions_for_component, get_capability_status

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

            new_entities: list[SmartThingsDynamicSwitch] = []

            for device_id, device in devices.items():
                dev_status = statuses.get(device_id) or {}
                comps_status = dev_status.get("components") or {}
                for comp_id, cap_versions in _iter_component_capabilities(device):
                    if comp_id not in comps_status:
                        continue

                    # Fetch capability definitions only for candidates that have any state attribute in status.
                    for capability_id, version in cap_versions.items():
                        cap_status = get_capability_status(data, device_id, comp_id, capability_id)
                        if not cap_status:
                            continue

                        # Candidate state attributes (common patterns)
                        candidate_state_attrs = [
                            a for a in ("switch", "activated", "enabled") if a in cap_status
                        ] + [
                            a for a, p in cap_status.items()
                            if isinstance(p, dict) and isinstance(p.get("value"), bool)
                        ]

                        if not candidate_state_attrs:
                            continue

                        try:
                            cap_def = await api.async_get_capability_definition(capability_id, version)
                        except Exception as err:  # noqa: BLE001
                            _LOGGER.debug("Could not fetch capability definition %s/%s: %s", capability_id, version, err)
                            continue

                        commands: dict[str, Any] = cap_def.get("commands") or {}

                        # Pattern 1: standard switch (on/off)
                        if "on" in commands and "off" in commands and "switch" in cap_status:
                            key = f"{device_id}|{comp_id}|{capability_id}|switch"
                            if key not in added:
                                added.add(key)
                                new_entities.append(
                                    SmartThingsDynamicSwitch(
                                        coordinator,
                                        api,
                                        entry_id=entry.entry_id,
                                        device=device,
                                        ref=EntityRef(
                                            device_id=device_id,
                                            component_id=comp_id,
                                            capability_id=capability_id,
                                            attribute="switch",
                                        ),
                                        on_cmd="on",
                                        off_cmd="off",
                                        state_attr="switch",
                                        name_suffix=_suffix(device, comp_id, capability_id, "switch"),
                                    )
                                )
                            continue

                        # Pattern 2: activate/deactivate (activated)
                        if "activate" in commands and "deactivate" in commands and "activated" in cap_status:
                            key = f"{device_id}|{comp_id}|{capability_id}|activated"
                            if key not in added:
                                added.add(key)
                                new_entities.append(
                                    SmartThingsDynamicSwitch(
                                        coordinator,
                                        api,
                                        entry_id=entry.entry_id,
                                        device=device,
                                        ref=EntityRef(
                                            device_id=device_id,
                                            component_id=comp_id,
                                            capability_id=capability_id,
                                            attribute="activated",
                                        ),
                                        on_cmd="activate",
                                        off_cmd="deactivate",
                                        state_attr="activated",
                                        name_suffix=_suffix(device, comp_id, capability_id, "activated"),
                                    )
                                )
                            continue

                        # Pattern 3: set* command with single boolean argument
                        for cmd_name, cmd_def in commands.items():
                            args = (cmd_def or {}).get("arguments") or []
                            if len(args) != 1:
                                continue
                            arg_schema = args[0].get("schema") or {}
                            if arg_schema.get("type") != "boolean":
                                continue
                            arg_name = args[0].get("name")
                            if not arg_name or arg_name not in cap_status:
                                continue

                            key = f"{device_id}|{comp_id}|{capability_id}|{arg_name}|{cmd_name}"
                            if key in added:
                                continue
                            added.add(key)

                            new_entities.append(
                                SmartThingsDynamicSwitch(
                                    coordinator,
                                    api,
                                    entry_id=entry.entry_id,
                                    device=device,
                                    ref=EntityRef(
                                        device_id=device_id,
                                        component_id=comp_id,
                                        capability_id=capability_id,
                                        attribute=str(arg_name),
                                    ),
                                    on_cmd=cmd_name,
                                    off_cmd=cmd_name,
                                    on_args=[True],
                                    off_args=[False],
                                    state_attr=str(arg_name),
                                    name_suffix=_suffix(device, comp_id, capability_id, str(arg_name)),
                                )
                            )

            if new_entities:
                _LOGGER.debug("Adding %d SmartThings Dynamic switch entities", len(new_entities))
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


def _suffix(device: dict[str, Any], component_id: str, capability_id: str, attr: str) -> str:
    # Keep entity name readable; prefer capability_id tail.
    cap_tail = capability_id.split(".")[-1]
    return f"{cap_tail}.{attr}"


class SmartThingsDynamicSwitch(SmartThingsDynamicBaseEntity, SwitchEntity):
    """Generic SmartThings switch-like capability."""

    def __init__(
        self,
        coordinator,
        api: SmartThingsApi,
        *,
        entry_id: str,
        device: dict[str, Any],
        ref: EntityRef,
        on_cmd: str,
        off_cmd: str,
        state_attr: str,
        on_args: list[Any] | None = None,
        off_args: list[Any] | None = None,
        name_suffix: str | None = None,
    ) -> None:
        super().__init__(coordinator, entry_id=entry_id, device=device, ref=ref, name_suffix=name_suffix)
        self._api = api
        self._on_cmd = on_cmd
        self._off_cmd = off_cmd
        self._on_args = on_args or []
        self._off_args = off_args or []
        self._state_attr = state_attr

    @property
    def is_on(self) -> bool | None:
        cap_status = get_capability_status(
            self.coordinator.data, self.ref.device_id, self.ref.component_id, self.ref.capability_id
        )
        payload = cap_status.get(self._state_attr) or {}
        if isinstance(payload, dict):
            return as_bool(payload.get("value"))
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._api.async_execute_command(
            self.ref.device_id,
            self.ref.component_id,
            self.ref.capability_id,
            self._on_cmd,
            self._on_args,
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._api.async_execute_command(
            self.ref.device_id,
            self.ref.component_id,
            self.ref.capability_id,
            self._off_cmd,
            self._off_args,
        )
        await self.coordinator.async_request_refresh()
