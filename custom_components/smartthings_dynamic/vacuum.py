"""Vacuum platform for SmartThings Dynamic (Samsung robot cleaners).

Home Assistant Core 2025.1+ replaced the old vacuum state constants with the VacuumActivity enum,
and VacuumEntity was superseded by StateVacuumEntity. This implementation follows the modern API.

Docs:
- https://developers.home-assistant.io/docs/core/entity/vacuum/
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.vacuum import (
    StateVacuumEntity,
    VacuumActivity,
    VacuumEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .api import SmartThingsApi
from .const import DOMAIN
from .entity import EntityRef, SmartThingsDynamicBaseEntity
from .helpers import get_capability_status

_LOGGER = logging.getLogger(__name__)

# Samsung robot cleaners expose a rich operating state in this custom capability.
VAC_CAP = "samsungce.robotCleanerOperatingState"
BAT_CAP = "battery"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator = runtime.coordinator
    api: SmartThingsApi = runtime.api

    added: set[str] = set()

    @callback
    def _async_discover() -> None:
        data = coordinator.data or {}
        devices: dict[str, Any] = data.get("devices") or {}

        new_entities: list[SmartThingsDynamicVacuum] = []

        for device_id, device in devices.items():
            cap_status = get_capability_status(data, device_id, "main", VAC_CAP)
            if not isinstance(cap_status, dict) or not cap_status:
                continue

            # Require at least an operatingState attribute to consider it a vacuum.
            if "operatingState" not in cap_status and "cleaningStep" not in cap_status:
                continue

            key = f"{device_id}|vacuum"
            if key in added:
                continue
            added.add(key)

            new_entities.append(
                SmartThingsDynamicVacuum(
                    coordinator,
                    api,
                    entry_id=entry.entry_id,
                    device=device,
                    ref=EntityRef(
                        device_id=device_id,
                        component_id="main",
                        capability_id=VAC_CAP,
                    ),
                )
            )

        if new_entities:
            _LOGGER.debug("Adding %d SmartThings Dynamic vacuum entities", len(new_entities))
            async_add_entities(new_entities)

    _async_discover()
    coordinator.async_add_listener(_async_discover)


def _map_operating_state_to_activity(state: str | None) -> VacuumActivity:
    if not state:
        return VacuumActivity.IDLE

    s = str(state).lower()

    # Error-ish
    if "error" in s or "fail" in s or "stuck" in s:
        return VacuumActivity.ERROR

    # Paused
    if "pause" in s:
        return VacuumActivity.PAUSED

    # Returning / homing
    if "home" in s or "return" in s or "homing" in s:
        return VacuumActivity.RETURNING

    # Docked / charging
    if "charge" in s or "dock" in s:
        return VacuumActivity.DOCKED

    # Cleaning-ish (Samsung adds many detailed states)
    if any(
        key in s
        for key in (
            "clean",
            "mop",
            "vacuum",
            "wash",
            "steriliz",
            "dry",
            "spin",
            "moving",
        )
    ):
        return VacuumActivity.CLEANING

    return VacuumActivity.IDLE


class SmartThingsDynamicVacuum(SmartThingsDynamicBaseEntity, StateVacuumEntity):
    """Vacuum entity mapped to SmartThings robot cleaner capabilities."""

    _attr_supported_features = (
        VacuumEntityFeature.STATE
        | VacuumEntityFeature.START
        | VacuumEntityFeature.PAUSE
        | VacuumEntityFeature.STOP
        | VacuumEntityFeature.RETURN_HOME
    )

    def __init__(
        self,
        coordinator,
        api: SmartThingsApi,
        *,
        entry_id: str,
        device: dict[str, Any],
        ref: EntityRef,
    ) -> None:
        SmartThingsDynamicBaseEntity.__init__(
            self,
            coordinator,
            entry_id=entry_id,
            device=device,
            ref=ref,
            name_suffix="vacuum",
        )
        self._api = api

    @property
    def activity(self) -> VacuumActivity:
        cap_status = get_capability_status(self.coordinator.data or {}, self.ref.device_id, "main", VAC_CAP)
        raw = (cap_status.get("operatingState") or {}).get("value") if isinstance(cap_status, dict) else None
        return _map_operating_state_to_activity(str(raw) if raw is not None else None)

    # Battery level is now handled by a separate sensor entity
    # This follows HA 2026.8+ deprecation guidelines

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        cap_status = get_capability_status(self.coordinator.data or {}, self.ref.device_id, "main", VAC_CAP)
        if not isinstance(cap_status, dict):
            return {}

        def _v(attr: str) -> Any:
            payload = cap_status.get(attr)
            if isinstance(payload, dict):
                return payload.get("value")
            return None

        data: dict[str, Any] = {}
        data["operating_state"] = _v("operatingState")
        data["cleaning_step"] = _v("cleaningStep")
        data["homing_reason"] = _v("homingReason")
        data["map_based_available"] = _v("isMapBasedOperationAvailable")
        
        # Add battery info to attributes if available
        bat_status = get_capability_status(self.coordinator.data or {}, self.ref.device_id, "main", BAT_CAP)
        if isinstance(bat_status, dict):
            battery = (bat_status.get("battery") or {}).get("value")
            if battery is not None:
                try:
                    data["battery_level"] = int(battery)
                except (TypeError, ValueError):
                    pass
        
        return {k: v for k, v in data.items() if v is not None}

    async def _try_cmd(self, command: str, args: list[Any] | None = None) -> bool:
        try:
            await self._api.async_execute_command(self.ref.device_id, "main", VAC_CAP, command, args or [])
            return True
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Vacuum command %s failed: %s", command, err)
            return False

    async def async_start(self) -> None:
        await self._try_cmd("start")
        await self.coordinator.async_request_refresh()

    async def async_pause(self) -> None:
        await self._try_cmd("pause")
        await self.coordinator.async_request_refresh()

    async def async_stop(self, **kwargs: Any) -> None:
        # Different robot models use different stop/cancel semantics; try in a safe order.
        for cmd in ("cancelRemainingJob", "stop", "cancel", "setOperatingState"):
            ok = await self._try_cmd(cmd)
            if ok:
                break
        await self.coordinator.async_request_refresh()

    async def async_return_to_base(self, **kwargs: Any) -> None:
        # Standard Samsung command name.
        if not await self._try_cmd("returnToHome"):
            # Fallbacks (best-effort)
            await self._try_cmd("return_to_home")
        await self.coordinator.async_request_refresh()