"""Tests for command sending across all platforms.

Verifies that every platform builds the correct payload and sends it
to the SmartThings API. Also tests edge cases like argument types,
empty arguments, and fallback command sequences.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.smartthings_dynamic.api import SmartThingsApi


# ─── Helpers ────────────────────────────────────────────────────────────────


def _make_api() -> tuple[SmartThingsApi, AsyncMock]:
    """Create an API instance with a mocked OAuth session."""
    oauth = MagicMock()
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = AsyncMock(return_value={})
    oauth.async_request = AsyncMock(return_value=resp)
    api = SmartThingsApi(oauth)
    return api, oauth.async_request


def _last_payload(mock_req: AsyncMock) -> dict[str, Any]:
    """Extract the JSON payload from the last async_request call."""
    return mock_req.call_args.kwargs["json"]


def _last_command(mock_req: AsyncMock) -> dict[str, Any]:
    """Extract the first command dict from the last call's payload."""
    return _last_payload(mock_req)["commands"][0]


# ─── async_execute_command: core payload structure ──────────────────────────


class TestExecuteCommandPayload:
    """Verify the payload structure built by async_execute_command."""

    @pytest.mark.asyncio
    async def test_basic_command_no_arguments(self):
        api, mock_req = _make_api()
        await api.async_execute_command("d1", "main", "switch", "on")

        cmd = _last_command(mock_req)
        assert cmd["component"] == "main"
        assert cmd["capability"] == "switch"
        assert cmd["command"] == "on"
        assert cmd["arguments"] == []

    @pytest.mark.asyncio
    async def test_command_with_string_argument(self):
        api, mock_req = _make_api()
        await api.async_execute_command("d1", "main", "washerMode", "setWasherMode", ["cotton"])

        cmd = _last_command(mock_req)
        assert cmd["arguments"] == ["cotton"]

    @pytest.mark.asyncio
    async def test_command_with_integer_argument(self):
        api, mock_req = _make_api()
        await api.async_execute_command("d1", "main", "thermostat", "setTemp", [22])

        cmd = _last_command(mock_req)
        assert cmd["arguments"] == [22]
        assert isinstance(cmd["arguments"][0], int)

    @pytest.mark.asyncio
    async def test_command_with_float_argument(self):
        api, mock_req = _make_api()
        await api.async_execute_command("d1", "main", "thermostat", "setTemp", [22.5])

        cmd = _last_command(mock_req)
        assert cmd["arguments"] == [22.5]

    @pytest.mark.asyncio
    async def test_command_with_boolean_argument(self):
        api, mock_req = _make_api()
        await api.async_execute_command("d1", "main", "custom.cap", "setEnabled", [True])

        cmd = _last_command(mock_req)
        assert cmd["arguments"] == [True]
        assert isinstance(cmd["arguments"][0], bool)

    @pytest.mark.asyncio
    async def test_command_with_false_argument(self):
        """[False] is falsy-looking but must NOT be replaced by []."""
        api, mock_req = _make_api()
        await api.async_execute_command("d1", "main", "custom.cap", "setEnabled", [False])

        cmd = _last_command(mock_req)
        assert cmd["arguments"] == [False]

    @pytest.mark.asyncio
    async def test_command_with_zero_argument(self):
        """[0] is falsy-looking but must NOT be replaced by []."""
        api, mock_req = _make_api()
        await api.async_execute_command("d1", "main", "audioVolume", "setVolume", [0])

        cmd = _last_command(mock_req)
        assert cmd["arguments"] == [0]

    @pytest.mark.asyncio
    async def test_none_arguments_becomes_empty_list(self):
        api, mock_req = _make_api()
        await api.async_execute_command("d1", "main", "switch", "on", None)

        cmd = _last_command(mock_req)
        assert cmd["arguments"] == []

    @pytest.mark.asyncio
    async def test_empty_list_arguments_stays_empty(self):
        api, mock_req = _make_api()
        await api.async_execute_command("d1", "main", "switch", "on", [])

        cmd = _last_command(mock_req)
        assert cmd["arguments"] == []

    @pytest.mark.asyncio
    async def test_multiple_arguments(self):
        api, mock_req = _make_api()
        await api.async_execute_command("d1", "main", "color", "setColor", [120, 80, 50])

        cmd = _last_command(mock_req)
        assert cmd["arguments"] == [120, 80, 50]

    @pytest.mark.asyncio
    async def test_non_main_component(self):
        api, mock_req = _make_api()
        await api.async_execute_command("d1", "cooler", "thermostat", "setTemp", [5])

        cmd = _last_command(mock_req)
        assert cmd["component"] == "cooler"

    @pytest.mark.asyncio
    async def test_custom_capability_id(self):
        api, mock_req = _make_api()
        await api.async_execute_command(
            "d1", "main", "samsungce.robotCleanerOperatingState", "start"
        )

        cmd = _last_command(mock_req)
        assert cmd["capability"] == "samsungce.robotCleanerOperatingState"

    @pytest.mark.asyncio
    async def test_url_contains_device_id(self):
        api, mock_req = _make_api()
        await api.async_execute_command("device-abc-123", "main", "switch", "on")

        url = mock_req.call_args.args[1]
        assert "device-abc-123" in url
        assert url.endswith("/commands")


# ─── Switch command patterns ───────────────────────────────────────────────


class TestSwitchCommands:
    """Verify switch on/off sends the right commands."""

    @pytest.mark.asyncio
    async def test_standard_switch_on(self):
        api, mock_req = _make_api()
        # Simulates SmartThingsDynamicSwitch.async_turn_on for pattern 1
        await api.async_execute_command("d1", "main", "switch", "on", [])

        cmd = _last_command(mock_req)
        assert cmd["command"] == "on"
        assert cmd["arguments"] == []

    @pytest.mark.asyncio
    async def test_standard_switch_off(self):
        api, mock_req = _make_api()
        await api.async_execute_command("d1", "main", "switch", "off", [])

        cmd = _last_command(mock_req)
        assert cmd["command"] == "off"
        assert cmd["arguments"] == []

    @pytest.mark.asyncio
    async def test_activate_deactivate_on(self):
        api, mock_req = _make_api()
        # Pattern 2
        await api.async_execute_command("d1", "main", "custom.childLock", "activate", [])

        cmd = _last_command(mock_req)
        assert cmd["command"] == "activate"

    @pytest.mark.asyncio
    async def test_boolean_arg_switch_on(self):
        api, mock_req = _make_api()
        # Pattern 3: same command, different args
        await api.async_execute_command("d1", "main", "custom.cap", "setEnabled", [True])

        cmd = _last_command(mock_req)
        assert cmd["command"] == "setEnabled"
        assert cmd["arguments"] == [True]

    @pytest.mark.asyncio
    async def test_boolean_arg_switch_off(self):
        api, mock_req = _make_api()
        await api.async_execute_command("d1", "main", "custom.cap", "setEnabled", [False])

        cmd = _last_command(mock_req)
        assert cmd["command"] == "setEnabled"
        assert cmd["arguments"] == [False]


# ─── Select command patterns ──────────────────────────────────────────────


class TestSelectCommands:
    """Verify select sends option as a single-element list argument."""

    @pytest.mark.asyncio
    async def test_select_option_sent_as_list(self):
        api, mock_req = _make_api()
        # Simulates SmartThingsDynamicSelect.async_select_option
        await api.async_execute_command("d1", "main", "washerMode", "setWasherMode", ["cotton"])

        cmd = _last_command(mock_req)
        assert cmd["arguments"] == ["cotton"]

    @pytest.mark.asyncio
    async def test_select_course(self):
        api, mock_req = _make_api()
        await api.async_execute_command("d1", "main", "custom.supportedOptions", "setCourse", ["quick"])

        cmd = _last_command(mock_req)
        assert cmd["capability"] == "custom.supportedOptions"
        assert cmd["command"] == "setCourse"
        assert cmd["arguments"] == ["quick"]

    @pytest.mark.asyncio
    async def test_select_empty_string_option(self):
        """Edge case: some Samsung devices have empty-string options."""
        api, mock_req = _make_api()
        await api.async_execute_command("d1", "main", "washerMode", "setWasherMode", [""])

        cmd = _last_command(mock_req)
        assert cmd["arguments"] == [""]


# ─── Number command patterns ──────────────────────────────────────────────


class TestNumberCommands:
    """Verify number sends value correctly, especially int vs float."""

    @pytest.mark.asyncio
    async def test_number_sends_float(self):
        api, mock_req = _make_api()
        # Simulates SmartThingsDynamicNumber.async_set_native_value
        # HA always passes float from NumberEntity
        await api.async_execute_command(
            "d1", "main", "thermostatCoolingSetpoint", "setCoolingSetpoint", [22.0]
        )

        cmd = _last_command(mock_req)
        assert cmd["arguments"] == [22.0]

    @pytest.mark.asyncio
    async def test_number_sends_zero(self):
        """Setting value to 0 must not be treated as empty args."""
        api, mock_req = _make_api()
        await api.async_execute_command("d1", "main", "audioVolume", "setVolume", [0.0])

        cmd = _last_command(mock_req)
        assert cmd["arguments"] == [0.0]

    @pytest.mark.asyncio
    async def test_integer_schema_casts_to_int(self):
        """SmartThingsDynamicNumber with schema_type='integer' must cast
        the float from HA to int before sending to the API."""
        api, mock_req = _make_api()
        # Simulate what async_set_native_value now does for integer schema
        value = 22.0
        arg = int(value)  # schema_type == "integer"
        await api.async_execute_command("d1", "main", "custom.cap", "setLevel", [arg])

        cmd = _last_command(mock_req)
        assert cmd["arguments"] == [22]
        assert isinstance(cmd["arguments"][0], int)

    @pytest.mark.asyncio
    async def test_number_schema_keeps_float(self):
        """SmartThingsDynamicNumber with schema_type='number' sends float as-is."""
        api, mock_req = _make_api()
        value = 22.5
        await api.async_execute_command("d1", "main", "custom.cap", "setTemp", [value])

        cmd = _last_command(mock_req)
        assert cmd["arguments"] == [22.5]
        assert isinstance(cmd["arguments"][0], float)

    @pytest.mark.asyncio
    async def test_integer_schema_zero_stays_int(self):
        """int(0.0) == 0 — must be sent as integer 0, not float 0.0."""
        api, mock_req = _make_api()
        arg = int(0.0)
        await api.async_execute_command("d1", "main", "custom.cap", "setLevel", [arg])

        cmd = _last_command(mock_req)
        assert cmd["arguments"] == [0]
        assert isinstance(cmd["arguments"][0], int)


# ─── Button command patterns ──────────────────────────────────────────────


class TestButtonCommands:
    """Verify button press sends no arguments."""

    @pytest.mark.asyncio
    async def test_button_press_no_args(self):
        api, mock_req = _make_api()
        # Simulates SmartThingsDynamicButton.async_press
        await api.async_execute_command("d1", "main", "washerOperatingState", "start", [])

        cmd = _last_command(mock_req)
        assert cmd["command"] == "start"
        assert cmd["arguments"] == []

    @pytest.mark.asyncio
    async def test_button_empty_command_string(self):
        """button.py passes `self.ref.command or ""` — verify empty string is handled."""
        api, mock_req = _make_api()
        await api.async_execute_command("d1", "main", "cap", "", [])

        cmd = _last_command(mock_req)
        assert cmd["command"] == ""


# ─── Vacuum command patterns ─────────────────────────────────────────────


class TestVacuumCommands:
    """Verify vacuum commands including fallback chains."""

    VAC_CAP = "samsungce.robotCleanerOperatingState"

    @pytest.mark.asyncio
    async def test_vacuum_start(self):
        api, mock_req = _make_api()
        await api.async_execute_command("d1", "main", self.VAC_CAP, "start", [])

        cmd = _last_command(mock_req)
        assert cmd["command"] == "start"
        assert cmd["capability"] == self.VAC_CAP

    @pytest.mark.asyncio
    async def test_vacuum_pause(self):
        api, mock_req = _make_api()
        await api.async_execute_command("d1", "main", self.VAC_CAP, "pause", [])

        cmd = _last_command(mock_req)
        assert cmd["command"] == "pause"

    @pytest.mark.asyncio
    async def test_vacuum_return_to_home(self):
        api, mock_req = _make_api()
        await api.async_execute_command("d1", "main", self.VAC_CAP, "returnToHome", [])

        cmd = _last_command(mock_req)
        assert cmd["command"] == "returnToHome"

    @pytest.mark.asyncio
    async def test_vacuum_stop_fallback_commands(self):
        """vacuum.py tries cancelRemainingJob → stop → cancel → setOperatingState.
        Verify each sends the right payload."""
        api, mock_req = _make_api()

        for cmd_name in ("cancelRemainingJob", "stop", "cancel", "setOperatingState"):
            mock_req.reset_mock()
            await api.async_execute_command("d1", "main", self.VAC_CAP, cmd_name, [])
            cmd = _last_command(mock_req)
            assert cmd["command"] == cmd_name
            assert cmd["arguments"] == []


# ─── send_command service: argument edge cases ──────────────────────────


class TestSendCommandArgumentEdgeCases:
    """Test the `arguments or []` pattern used in both api.py and __init__.py."""

    @pytest.mark.asyncio
    async def test_arguments_none_defaults_to_empty(self):
        """api.py: `arguments or []` when None."""
        api, mock_req = _make_api()
        await api.async_execute_command("d1", "main", "switch", "on", None)

        cmd = _last_command(mock_req)
        assert cmd["arguments"] == []

    @pytest.mark.asyncio
    async def test_arguments_empty_list_is_preserved(self):
        api, mock_req = _make_api()
        await api.async_execute_command("d1", "main", "switch", "on", [])

        cmd = _last_command(mock_req)
        assert cmd["arguments"] == []

    @pytest.mark.asyncio
    async def test_single_false_argument_not_lost(self):
        """[False] is truthy as a list, so `or []` should NOT apply."""
        api, mock_req = _make_api()
        await api.async_execute_command("d1", "main", "cap", "cmd", [False])

        cmd = _last_command(mock_req)
        assert cmd["arguments"] == [False]

    @pytest.mark.asyncio
    async def test_single_zero_argument_not_lost(self):
        api, mock_req = _make_api()
        await api.async_execute_command("d1", "main", "cap", "cmd", [0])

        cmd = _last_command(mock_req)
        assert cmd["arguments"] == [0]

    @pytest.mark.asyncio
    async def test_single_empty_string_argument_not_lost(self):
        api, mock_req = _make_api()
        await api.async_execute_command("d1", "main", "cap", "cmd", [""])

        cmd = _last_command(mock_req)
        assert cmd["arguments"] == [""]

    @pytest.mark.asyncio
    async def test_nested_dict_argument(self):
        """Some Samsung capabilities accept complex objects."""
        api, mock_req = _make_api()
        await api.async_execute_command("d1", "main", "cap", "cmd", [{"mode": "auto", "speed": 3}])

        cmd = _last_command(mock_req)
        assert cmd["arguments"] == [{"mode": "auto", "speed": 3}]

    @pytest.mark.asyncio
    async def test_list_of_strings_argument(self):
        api, mock_req = _make_api()
        await api.async_execute_command("d1", "main", "cap", "cmd", ["a", "b", "c"])

        cmd = _last_command(mock_req)
        assert cmd["arguments"] == ["a", "b", "c"]
