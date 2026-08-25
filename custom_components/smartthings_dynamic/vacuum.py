"""Vacuum platform for SmartThings Dynamic (Samsung robot cleaners).

Home Assistant Core 2025.1+ replaced the old vacuum state constants with the VacuumActivity enum,
and VacuumEntity was superseded by StateVacuumEntity. This implementation follows the modern API.

Docs:
- https://developers.home-assistant.io/docs/core/entity/vacuum/
"""

from __future__ import annotations

import logging
from contextlib import suppress
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

# Companion capabilities that mirror what the SmartThings mobile app offers.
TURBO_CAP = "robotCleanerTurboMode"
TYPE_CAP = "samsungce.robotCleanerCleaningType"
WATER_CAP = "samsungce.robotCleanerWaterSprayLevel"
DRIVING_CAP = "samsungce.robotCleanerDrivingMode"
MODE_CAP = "samsungce.robotCleanerCleaningMode"
AREA_INFO_CAP = "samsungce.robotCleanerMapAreaInfo"
MAP_INFO_CAP = "samsungce.robotCleanerMapCleaningInfo"

# robotCleanerTurboMode publishes no "supported values" attribute, so we fall back to
# the values Samsung robot cleaners use. The reported value is always included as well.
TURBO_MODES: tuple[str, ...] = ("extraSilence", "silence", "off", "on")


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

    # Docked / charging ("charging", "charged", "chargingForRemainingJob", "flexCharged", ...)
    if "charg" in s or "dock" in s:
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

        features = (
            VacuumEntityFeature.STATE
            | VacuumEntityFeature.START
            | VacuumEntityFeature.PAUSE
            | VacuumEntityFeature.STOP
            | VacuumEntityFeature.RETURN_HOME
        )
        if self._cap(TURBO_CAP):
            features |= VacuumEntityFeature.FAN_SPEED
        self._attr_supported_features = features

    # --- capability access -------------------------------------------------

    def _cap(self, capability_id: str) -> dict[str, Any]:
        cap_status = get_capability_status(
            self.coordinator.data or {}, self.ref.device_id, "main", capability_id
        )
        return cap_status if isinstance(cap_status, dict) else {}

    def _value(self, capability_id: str, attribute: str) -> Any:
        payload = self._cap(capability_id).get(attribute)
        if isinstance(payload, dict):
            return payload.get("value")
        return None

    # --- state -------------------------------------------------------------

    @property
    def activity(self) -> VacuumActivity:
        raw = self._value(VAC_CAP, "operatingState")
        return _map_operating_state_to_activity(str(raw) if raw is not None else None)

    # Battery level is now handled by a separate sensor entity
    # This follows HA 2026.8+ deprecation guidelines

    # --- suction power (robotCleanerTurboMode) -----------------------------

    @property
    def fan_speed(self) -> str | None:
        value = self._value(TURBO_CAP, "robotCleanerTurboMode")
        return str(value) if value is not None else None

    @property
    def fan_speed_list(self) -> list[str]:
        if not self._cap(TURBO_CAP):
            return []
        options = list(TURBO_MODES)
        current = self.fan_speed
        if current is not None and current not in options:
            options.append(current)
        return options

    async def async_set_fan_speed(self, fan_speed: str, **kwargs: Any) -> None:
        await self._try_cmd("setRobotCleanerTurboMode", [fan_speed], capability=TURBO_CAP)
        await self.coordinator.async_request_refresh()

    # --- attributes --------------------------------------------------------

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "operating_state": self._value(VAC_CAP, "operatingState"),
            "cleaning_step": self._value(VAC_CAP, "cleaningStep"),
            "homing_reason": self._value(VAC_CAP, "homingReason"),
            "map_based_available": self._value(VAC_CAP, "isMapBasedOperationAvailable"),
            # Mirrors of the mobile app's cleaning options.
            "cleaning_mode": self._value(MODE_CAP, "cleaningMode"),
            "cleaning_type": self._value(TYPE_CAP, "cleaningType"),
            "water_spray_level": self._value(WATER_CAP, "waterSprayLevel"),
            "driving_mode": self._value(DRIVING_CAP, "drivingMode"),
            # Map info is read-only in the SmartThings API – see docs/samsung-robot-cleaner.md
            "map_areas": self._value(AREA_INFO_CAP, "areaInfo"),
            "current_area": self._value(MAP_INFO_CAP, "area"),
            "cleaned_extent": self._value(MAP_INFO_CAP, "cleanedExtent"),
            "remaining_time": self._value(MAP_INFO_CAP, "remainingTime"),
        }

        battery = self._value(BAT_CAP, "battery")
        if battery is not None:
            with suppress(TypeError, ValueError):
                data["battery_level"] = int(battery)

        return {k: v for k, v in data.items() if v is not None}

    # --- commands ----------------------------------------------------------

    async def _try_cmd(
        self,
        command: str,
        args: list[Any] | None = None,
        *,
        capability: str = VAC_CAP,
    ) -> bool:
        try:
            await self._api.async_execute_command(
                self.ref.device_id, "main", capability, command, args or []
            )
            return True
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Vacuum command %s failed: %s", command, err)
            return False

    async def async_start(self) -> None:
        # A paused robot has to be resumed; `start` restarts the job from scratch.
        if self.activity == VacuumActivity.PAUSED and await self._try_cmd("resume"):
            await self.coordinator.async_request_refresh()
            return
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
