"""Button platform for SmartThings Dynamic (exposes no-argument commands)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .api import SmartThingsApi
from .const import CONF_EXPOSE_COMMAND_BUTTONS, DOMAIN
from .entity import EntityRef, SmartThingsDynamicBaseEntity
from .helpers import capability_versions_for_component

_LOGGER = logging.getLogger(__name__)


SKIP_COMMANDS = {"on", "off", "activate", "deactivate"}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    if not bool(entry.options.get(CONF_EXPOSE_COMMAND_BUTTONS, True)):
        _LOGGER.debug("Command buttons are disabled by options")
        return

    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator = runtime.coordinator
    api: SmartThingsApi = runtime.api

    added: set[str] = set()
    lock = asyncio.Lock()

    async def _async_discover() -> None:
        async with lock:
            data = coordinator.data or {}
            devices: dict[str, Any] = data.get("devices") or {}

            new_entities: list[SmartThingsDynamicButton] = []

            for device_id, device in devices.items():
                for comp_id, caps in _iter_component_capabilities(device):
                    for cap_id, version in caps.items():
                        try:
                            cap_def = await api.async_get_capability_definition(cap_id, version)
                        except Exception as err:  # noqa: BLE001
                            _LOGGER.debug("Could not fetch capability definition %s/%s: %s", cap_id, version, err)
                            continue

                        commands: dict[str, Any] = cap_def.get("commands") or {}
                        for cmd_name, cmd_def in commands.items():
                            if cmd_name in SKIP_COMMANDS:
                                continue
                            args = (cmd_def or {}).get("arguments") or []
                            if args:
                                continue  # only no-argument commands

                            key = f"{device_id}|{comp_id}|{cap_id}|{cmd_name}"
                            if key in added:
                                continue
                            added.add(key)

                            cap_tail = cap_id.split(".")[-1]
                            suffix = f"{cap_tail}.{cmd_name}"
                            new_entities.append(
                                SmartThingsDynamicButton(
                                    coordinator,
                                    api,
                                    entry_id=entry.entry_id,
                                    device=device,
                                    ref=EntityRef(
                                        device_id=device_id,
                                        component_id=comp_id,
                                        capability_id=cap_id,
                                        command=cmd_name,
                                    ),
                                    name_suffix=suffix,
                                )
                            )

            if new_entities:
                _LOGGER.debug("Adding %d SmartThings Dynamic button entities", len(new_entities))
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


class SmartThingsDynamicButton(SmartThingsDynamicBaseEntity, ButtonEntity):
    """Button that triggers a SmartThings command without arguments."""

    def __init__(
        self,
        coordinator,
        api: SmartThingsApi,
        *,
        entry_id: str,
        device: dict[str, Any],
        ref: EntityRef,
        name_suffix: str | None = None,
    ) -> None:
        super().__init__(coordinator, entry_id=entry_id, device=device, ref=ref, name_suffix=name_suffix)
        self._api = api

    async def async_press(self) -> None:
        await self._api.async_execute_command(
            self.ref.device_id,
            self.ref.component_id,
            self.ref.capability_id,
            self.ref.command or "",
            [],
        )
        await self.coordinator.async_request_refresh()
