"""Tests for the vacuum platform (Samsung robot cleaners).

Covers the capabilities the SmartThings API actually exposes for a Samsung robot
cleaner: operating state, suction power (robotCleanerTurboMode) and the read-only
cleaning options mirrored into entity attributes.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.smartthings_dynamic.entity import EntityRef
from custom_components.smartthings_dynamic.vacuum import (
    TURBO_MODES,
    VAC_CAP,
    SmartThingsDynamicVacuum,
    _map_operating_state_to_activity,
)

DEVICE_ID = "d3adac46-506b-931c-ce10-5314e0282074"


def _status(**caps: dict[str, Any]) -> dict[str, Any]:
    """Build coordinator data with the given capability statuses on `main`."""
    return {
        "devices": {DEVICE_ID: {"deviceId": DEVICE_ID, "label": "Bestia", "components": []}},
        "status": {DEVICE_ID: {"components": {"main": caps}}},
    }


def _make_vacuum(data: dict[str, Any]) -> tuple[SmartThingsDynamicVacuum, AsyncMock]:
    coordinator = MagicMock()
    coordinator.data = data
    coordinator.async_request_refresh = AsyncMock()

    api = MagicMock()
    api.async_execute_command = AsyncMock()

    vacuum = SmartThingsDynamicVacuum(
        coordinator,
        api,
        entry_id="entry1",
        device=data["devices"][DEVICE_ID],
        ref=EntityRef(device_id=DEVICE_ID, component_id="main", capability_id=VAC_CAP),
    )
    return vacuum, api.async_execute_command


def _sent(mock_cmd: AsyncMock) -> tuple[str, str, list[Any]]:
    """Return (capability, command, arguments) of the last command sent."""
    args = mock_cmd.call_args.args
    return args[2], args[3], args[4]


# ─── Operating state mapping ───────────────────────────────────────────────


class TestOperatingStateMapping:
    @pytest.mark.parametrize(
        "state",
        ["cleaning", "moving", "washingMop", "dryingMop", "spinDrying"],
    )
    def test_active_states_map_to_cleaning(self, state):
        from homeassistant.components.vacuum import VacuumActivity

        assert _map_operating_state_to_activity(state) == VacuumActivity.CLEANING

    def test_charging_maps_to_docked(self):
        from homeassistant.components.vacuum import VacuumActivity

        assert _map_operating_state_to_activity("charging") == VacuumActivity.DOCKED

    def test_homing_maps_to_returning(self):
        from homeassistant.components.vacuum import VacuumActivity

        assert _map_operating_state_to_activity("homing") == VacuumActivity.RETURNING

    def test_none_maps_to_idle(self):
        from homeassistant.components.vacuum import VacuumActivity

        assert _map_operating_state_to_activity(None) == VacuumActivity.IDLE


# ─── Suction power via robotCleanerTurboMode ───────────────────────────────


class TestFanSpeed:
    def test_fan_speed_reads_turbo_mode(self):
        vacuum, _ = _make_vacuum(
            _status(**{"robotCleanerTurboMode": {"robotCleanerTurboMode": {"value": "silence"}}})
        )
        assert vacuum.fan_speed == "silence"

    def test_fan_speed_list_contains_known_modes(self):
        vacuum, _ = _make_vacuum(
            _status(**{"robotCleanerTurboMode": {"robotCleanerTurboMode": {"value": "on"}}})
        )
        assert vacuum.fan_speed_list == list(TURBO_MODES)

    def test_unknown_current_mode_is_added_to_list(self):
        vacuum, _ = _make_vacuum(
            _status(**{"robotCleanerTurboMode": {"robotCleanerTurboMode": {"value": "maxPlus"}}})
        )
        assert "maxPlus" in vacuum.fan_speed_list

    def test_no_turbo_capability_means_no_fan_speed(self):
        vacuum, _ = _make_vacuum(_status(**{VAC_CAP: {"operatingState": {"value": "charging"}}}))
        assert vacuum.fan_speed is None
        assert vacuum.fan_speed_list == []

    @pytest.mark.asyncio
    async def test_set_fan_speed_sends_turbo_command(self):
        vacuum, mock_cmd = _make_vacuum(
            _status(**{"robotCleanerTurboMode": {"robotCleanerTurboMode": {"value": "off"}}})
        )
        await vacuum.async_set_fan_speed("silence")

        capability, command, arguments = _sent(mock_cmd)
        assert capability == "robotCleanerTurboMode"
        assert command == "setRobotCleanerTurboMode"
        assert arguments == ["silence"]


# ─── Cleaning options mirrored into attributes ─────────────────────────────


class TestExtraStateAttributes:
    def _full_status(self) -> dict[str, Any]:
        return _status(
            **{
                VAC_CAP: {
                    "operatingState": {"value": "charging"},
                    "isMapBasedOperationAvailable": {"value": False},
                },
                "samsungce.robotCleanerCleaningType": {"cleaningType": {"value": "mop"}},
                "samsungce.robotCleanerWaterSprayLevel": {"waterSprayLevel": {"value": "high"}},
                "samsungce.robotCleanerDrivingMode": {"drivingMode": {"value": "areaThenWalls"}},
                "samsungce.robotCleanerCleaningMode": {"cleaningMode": {"value": "stop"}},
                "samsungce.robotCleanerMapAreaInfo": {
                    "areaInfo": {"value": [{"id": "5", "name": "Kitchen"}]}
                },
                "samsungce.robotCleanerMapCleaningInfo": {"remainingTime": {"value": -1}},
                "battery": {"battery": {"value": 77}},
            }
        )

    def test_cleaning_options_are_exposed(self):
        vacuum, _ = _make_vacuum(self._full_status())
        attrs = vacuum.extra_state_attributes

        assert attrs["cleaning_type"] == "mop"
        assert attrs["water_spray_level"] == "high"
        assert attrs["driving_mode"] == "areaThenWalls"
        assert attrs["cleaning_mode"] == "stop"

    def test_map_areas_are_exposed(self):
        vacuum, _ = _make_vacuum(self._full_status())
        assert vacuum.extra_state_attributes["map_areas"] == [{"id": "5", "name": "Kitchen"}]

    def test_battery_level_is_an_int(self):
        vacuum, _ = _make_vacuum(self._full_status())
        assert vacuum.extra_state_attributes["battery_level"] == 77

    def test_missing_values_are_dropped(self):
        vacuum, _ = _make_vacuum(_status(**{VAC_CAP: {"operatingState": {"value": "charging"}}}))
        attrs = vacuum.extra_state_attributes

        assert attrs == {"operating_state": "charging"}


# ─── Start / resume semantics ──────────────────────────────────────────────


class TestStartCommands:
    @pytest.mark.asyncio
    async def test_start_from_dock_sends_start(self):
        vacuum, mock_cmd = _make_vacuum(_status(**{VAC_CAP: {"operatingState": {"value": "charging"}}}))
        await vacuum.async_start()

        capability, command, _ = _sent(mock_cmd)
        assert capability == VAC_CAP
        assert command == "start"

    @pytest.mark.asyncio
    async def test_start_while_paused_sends_resume(self):
        vacuum, mock_cmd = _make_vacuum(_status(**{VAC_CAP: {"operatingState": {"value": "paused"}}}))
        await vacuum.async_start()

        assert mock_cmd.call_count == 1
        _, command, _ = _sent(mock_cmd)
        assert command == "resume"

    @pytest.mark.asyncio
    async def test_resume_failure_falls_back_to_start(self):
        vacuum, mock_cmd = _make_vacuum(_status(**{VAC_CAP: {"operatingState": {"value": "paused"}}}))
        mock_cmd.side_effect = [RuntimeError("boom"), None]

        await vacuum.async_start()

        commands = [call.args[3] for call in mock_cmd.call_args_list]
        assert commands == ["resume", "start"]
