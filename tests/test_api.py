"""Tests for the SmartThings API client."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import ClientResponseError

from custom_components.smartthings_dynamic.api import DEFAULT_HEADERS, SmartThingsApi
from custom_components.smartthings_dynamic.const import SMARTTHINGS_API_BASE


# ─── Helpers ────────────────────────────────────────────────────────────────


class FakeResponse:
    """Minimal response object returned by OAuth2Session.async_request."""

    def __init__(self, data: Any, status: int = 200) -> None:
        self._data = data
        self.status = status

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise ClientResponseError(
                request_info=MagicMock(),
                history=(),
                status=self.status,
                message="Error",
            )

    async def json(self) -> Any:
        return self._data


def _make_api(response: FakeResponse | None = None) -> tuple[SmartThingsApi, AsyncMock]:
    """Create an API client with a mocked OAuth2 session."""
    oauth_session = MagicMock()
    oauth_session.async_request = AsyncMock(return_value=response or FakeResponse({}))
    api = SmartThingsApi(oauth_session)
    return api, oauth_session.async_request


# ─── async_list_devices ─────────────────────────────────────────────────────


class TestAsyncListDevices:
    @pytest.mark.asyncio
    async def test_calls_correct_endpoint(self):
        payload = {"items": [{"deviceId": "d1"}]}
        api, mock_req = _make_api(FakeResponse(payload))

        result = await api.async_list_devices()

        mock_req.assert_called_once_with(
            "get",
            f"{SMARTTHINGS_API_BASE}/devices",
            headers=DEFAULT_HEADERS,
            json=None,
        )
        assert result == payload

    @pytest.mark.asyncio
    async def test_auth_error_raises_config_entry_auth_failed(self):
        api, _ = _make_api(FakeResponse({}, status=401))

        with pytest.raises(Exception, match="authentication failed"):
            await api.async_list_devices()

    @pytest.mark.asyncio
    async def test_403_raises_config_entry_auth_failed(self):
        api, _ = _make_api(FakeResponse({}, status=403))

        with pytest.raises(Exception, match="authentication failed"):
            await api.async_list_devices()

    @pytest.mark.asyncio
    async def test_500_raises_client_response_error(self):
        api, _ = _make_api(FakeResponse({}, status=500))

        with pytest.raises(ClientResponseError):
            await api.async_list_devices()


# ─── async_get_device ───────────────────────────────────────────────────────


class TestAsyncGetDevice:
    @pytest.mark.asyncio
    async def test_calls_correct_endpoint(self):
        device_data = {"deviceId": "d1", "label": "Test"}
        api, mock_req = _make_api(FakeResponse(device_data))

        result = await api.async_get_device("d1")

        mock_req.assert_called_once_with(
            "get",
            f"{SMARTTHINGS_API_BASE}/devices/d1",
            headers=DEFAULT_HEADERS,
            json=None,
        )
        assert result == device_data


# ─── async_get_device_status ────────────────────────────────────────────────


class TestAsyncGetDeviceStatus:
    @pytest.mark.asyncio
    async def test_calls_correct_endpoint(self):
        status = {"components": {"main": {}}}
        api, mock_req = _make_api(FakeResponse(status))

        result = await api.async_get_device_status("d1")

        mock_req.assert_called_once_with(
            "get",
            f"{SMARTTHINGS_API_BASE}/devices/d1/status",
            headers=DEFAULT_HEADERS,
            json=None,
        )
        assert result == status


# ─── async_execute_command ──────────────────────────────────────────────────


class TestAsyncExecuteCommand:
    @pytest.mark.asyncio
    async def test_sends_correct_payload(self):
        api, mock_req = _make_api(FakeResponse({}))

        await api.async_execute_command(
            device_id="d1",
            component="main",
            capability="switch",
            command="on",
        )

        expected_payload = {
            "commands": [
                {
                    "component": "main",
                    "capability": "switch",
                    "command": "on",
                    "arguments": [],
                }
            ]
        }
        mock_req.assert_called_once_with(
            "post",
            f"{SMARTTHINGS_API_BASE}/devices/d1/commands",
            headers=DEFAULT_HEADERS,
            json=expected_payload,
        )

    @pytest.mark.asyncio
    async def test_sends_arguments(self):
        api, mock_req = _make_api(FakeResponse({}))

        await api.async_execute_command(
            device_id="d1",
            component="main",
            capability="thermostatCoolingSetpoint",
            command="setCoolingSetpoint",
            arguments=[22],
        )

        call_args = mock_req.call_args
        payload = call_args.kwargs["json"]
        assert payload["commands"][0]["arguments"] == [22]

    @pytest.mark.asyncio
    async def test_auth_error_propagates(self):
        api, _ = _make_api(FakeResponse({}, status=401))

        with pytest.raises(Exception, match="authentication failed"):
            await api.async_execute_command("d1", "main", "switch", "on")


# ─── async_get_capability_definition ────────────────────────────────────────


class TestAsyncGetCapabilityDefinition:
    @pytest.mark.asyncio
    async def test_fetches_and_caches(self):
        cap_def = {"id": "switch", "version": 1, "attributes": {}, "commands": {}}
        api, mock_req = _make_api(FakeResponse(cap_def))

        # First call fetches
        result1 = await api.async_get_capability_definition("switch", 1)
        assert result1 == cap_def
        assert mock_req.call_count == 1

        # Second call returns from cache
        result2 = await api.async_get_capability_definition("switch", 1)
        assert result2 == cap_def
        assert mock_req.call_count == 1  # no additional request

    @pytest.mark.asyncio
    async def test_different_versions_cached_separately(self):
        api, mock_req = _make_api(FakeResponse({"id": "cap", "version": 1}))

        await api.async_get_capability_definition("cap", 1)
        # Change mock response for v2
        mock_req.return_value = FakeResponse({"id": "cap", "version": 2})
        await api.async_get_capability_definition("cap", 2)

        assert mock_req.call_count == 2

    @pytest.mark.asyncio
    async def test_correct_endpoint(self):
        api, mock_req = _make_api(FakeResponse({}))

        await api.async_get_capability_definition("custom.washerMode", 1)

        mock_req.assert_called_once_with(
            "get",
            f"{SMARTTHINGS_API_BASE}/capabilities/custom.washerMode/1",
            headers=DEFAULT_HEADERS,
            json=None,
        )


# ─── DEFAULT_HEADERS ────────────────────────────────────────────────────────


class TestDefaultHeaders:
    def test_accept_header(self):
        assert "smartthings" in DEFAULT_HEADERS["Accept"]

    def test_content_type(self):
        assert DEFAULT_HEADERS["Content-Type"] == "application/json"
