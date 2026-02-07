"""Select platform for SmartThings Dynamic (enum-like controls)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .api import SmartThingsApi
from .const import DOMAIN, CONF_AGGRESSIVE_MODE, DEFAULT_AGGRESSIVE_MODE
from .entity import EntityRef, SmartThingsDynamicBaseEntity
from .helpers import capability_versions_for_component, get_capability_status

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator = runtime.coordinator
    api: SmartThingsApi = runtime.api

    added: set[str] = set()

    aggressive = bool(entry.options.get(CONF_AGGRESSIVE_MODE, DEFAULT_AGGRESSIVE_MODE))
    lock = asyncio.Lock()

    async def _async_discover() -> None:
        async with lock:
            data = coordinator.data or {}
            devices: dict[str, Any] = data.get("devices") or {}
            statuses: dict[str, Any] = data.get("status") or {}

            new_entities: list[SmartThingsDynamicSelect] = []

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

                        # Special-case: Samsung appliances often expose course selection via custom.supportedOptions
                        if cap_id == "custom.supportedOptions":
                            supported = _list_value(cap_status, "supportedCourses")
                            current = _scalar_value(cap_status, "course")
                            if supported and "setCourse" in commands:
                                key = f"{device_id}|{comp_id}|{cap_id}|course|setCourse"
                                if key not in added:
                                    added.add(key)
                                    new_entities.append(
                                        SmartThingsDynamicSelect(
                                            coordinator,
                                            api,
                                            entry_id=entry.entry_id,
                                            device=device,
                                            ref=EntityRef(
                                                device_id=device_id,
                                                component_id=comp_id,
                                                capability_id=cap_id,
                                                attribute="course",
                                            ),
                                            command="setCourse",
                                            options=supported,
                                            name_suffix="course",
                                        )
                                    )

                        # Schema-driven: any command with a single enum argument becomes a Select
                        for cmd_name, cmd_def in commands.items():
                            args = (cmd_def or {}).get("arguments") or []
                            if len(args) != 1:
                                continue
                            arg = args[0]
                            arg_name = arg.get("name")
                            schema = (arg.get("schema") or {})
                            enum = schema.get("enum")
                            if not arg_name or not enum or not isinstance(enum, list):
                                continue
                            # Need a readable current value from status
                            if arg_name not in cap_status:
                                continue

                            options = [str(v) for v in enum]
                            # Include current value even if it isn't in enum (happens sometimes)
                            current_val = _scalar_value(cap_status, arg_name)
                            if current_val is not None and str(current_val) not in options:
                                options = [str(current_val)] + options

                            key = f"{device_id}|{comp_id}|{cap_id}|{arg_name}|{cmd_name}"
                            if key in added:
                                continue
                            added.add(key)

                            suffix = _suffix(device, comp_id, cap_id, arg_name)
                            new_entities.append(
                                SmartThingsDynamicSelect(
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
                                    options=options,
                                    name_suffix=suffix,
                                )
                            )

                        # Heuristic controls (aggressive mode): create selects from supported* lists
                        if aggressive:
                            new_entities.extend(
                                _supported_list_selects(
                                    coordinator=coordinator,
                                    api=api,
                                    entry_id=entry.entry_id,
                                    device_id=device_id,
                                    device=device,
                                    comp_id=comp_id,
                                    cap_id=cap_id,
                                    cap_status=cap_status,
                                    commands=commands,
                                    added=added,
                                )
                            )


            if new_entities:
                _LOGGER.debug("Adding %d SmartThings Dynamic select entities", len(new_entities))
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


def _list_value(cap_status: dict[str, Any], attr: str) -> list[str] | None:
    payload = cap_status.get(attr)
    if isinstance(payload, dict):
        v = payload.get("value")
        if isinstance(v, list):
            return [str(x) for x in v]
    return None


def _scalar_value(cap_status: dict[str, Any], attr: str) -> Any:
    payload = cap_status.get(attr)
    if isinstance(payload, dict):
        return payload.get("value")
    return None


def _suffix(device: dict[str, Any], component_id: str, capability_id: str, attr: str) -> str:
    """Build a concise suffix for entity name."""
    cap_tail = capability_id.split(".")[-1]
    if component_id != "main":
        return f"{component_id}.{cap_tail}.{attr}"
    return f"{cap_tail}.{attr}"


def _infer_current_attr_from_supported_attr(cap_status: dict[str, Any], supported_attr: str) -> str | None:
    """Try to map a supported* attribute to its corresponding current attribute.

    Examples:
    - supportedModes -> mode
    - supportedWasherSpinLevel -> washerSpinLevel
    """
    if not supported_attr.startswith("supported"):
        return None

    tail = supported_attr[len("supported") :]
    if not tail:
        return None

    # Convert leading capital to lower: Modes -> modes, WasherSpinLevel -> washerSpinLevel
    cand = tail[0].lower() + tail[1:]

    # Direct match
    if cand in cap_status:
        return cand

    # Common plural forms: modes -> mode
    if cand.endswith("s") and cand[:-1] in cap_status:
        return cand[:-1]
    if cand.endswith("es") and cand[:-2] in cap_status:
        return cand[:-2]
    if cand.endswith("ies") and (cand[:-3] + "y") in cap_status:
        return cand[:-3] + "y"

    return None


def _supported_list_selects(
    *,
    coordinator,
    api: SmartThingsApi,
    entry_id: str,
    device_id: str,
    device: dict[str, Any],
    comp_id: str,
    cap_id: str,
    cap_status: dict[str, Any],
    commands: dict[str, Any],
    added: set[str],
) -> list["SmartThingsDynamicSelect"]:
    """Create Select entities from supported* lists even if the command schema is not enum-based.

    Samsung appliances often expose supported values in `supportedXxx` attributes while the command argument
    is a generic string type.
    """
    entities: list[SmartThingsDynamicSelect] = []

    for attr_name in cap_status:
        if not attr_name.startswith("supported"):
            continue

        options = _list_value(cap_status, attr_name)
        if not options:
            continue

        # Avoid creating extremely large selects by default; users can still enable schema-driven controls.
        if len(options) > 80:
            continue

        current_attr = _infer_current_attr_from_supported_attr(cap_status, attr_name)
        if not current_attr:
            continue

        # Require a current value to exist (prevents a lot of false positives)
        if _scalar_value(cap_status, current_attr) is None:
            continue

        cmd_name = f"set{current_attr[0].upper()}{current_attr[1:]}"
        cmd_def = commands.get(cmd_name) or {}
        args = (cmd_def or {}).get("arguments") or []
        if cmd_name not in commands or len(args) != 1:
            continue

        key = f"{device_id}|{comp_id}|{cap_id}|{current_attr}|{cmd_name}"
        if key in added:
            continue
        added.add(key)

        suffix = _suffix(device, comp_id, cap_id, current_attr)

        ent = SmartThingsDynamicSelect(
            coordinator,
            api,
            entry_id=entry_id,
            device=device,
            ref=EntityRef(
                device_id=device_id,
                component_id=comp_id,
                capability_id=cap_id,
                attribute=current_attr,
            ),
            command=cmd_name,
            options=options,
            name_suffix=suffix,
        )

        # If there are many options, disable by default to avoid overwhelming the UI.
        if len(options) > 30:
            ent._attr_entity_registry_enabled_default = False  # type: ignore[attr-defined]

        entities.append(ent)

    return entities


class SmartThingsDynamicSelect(SmartThingsDynamicBaseEntity, SelectEntity):
    """Select entity mapped to a SmartThings command with a single enum argument."""

    def __init__(
        self,
        coordinator,
        api: SmartThingsApi,
        *,
        entry_id: str,
        device: dict[str, Any],
        ref: EntityRef,
        command: str,
        options: list[str],
        name_suffix: str | None = None,
    ) -> None:
        super().__init__(coordinator, entry_id=entry_id, device=device, ref=ref, name_suffix=name_suffix)
        self._api = api
        self._command = command
        self._options = options

    @property
    def options(self) -> list[str]:
        return self._options

    @property
    def current_option(self) -> str | None:
        val = self._attr_value()
        return str(val) if val is not None else None

    async def async_select_option(self, option: str) -> None:
        await self._api.async_execute_command(
            self.ref.device_id,
            self.ref.component_id,
            self.ref.capability_id,
            self._command,
            [option],
        )
        await self.coordinator.async_request_refresh()