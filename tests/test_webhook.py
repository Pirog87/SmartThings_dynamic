"""Tests for the SmartThings Dynamic webhook module."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.smartthings_dynamic.webhook import (
    _async_handle_webhook,
    _process_device_events,
    _webhook_id_for_entry,
    async_register_webhook,
    async_unregister_webhook,
    webhook_url,
)

# ---------------------------------------------------------------------------
# _webhook_id_for_entry
# ---------------------------------------------------------------------------


class TestWebhookIdForEntry:
    """Tests for deterministic webhook ID generation."""

    def test_returns_hex_string(self):
        wh_id = _webhook_id_for_entry("entry-abc")
        assert isinstance(wh_id, str)
        assert len(wh_id) == 32
        # Must be valid hex
        int(wh_id, 16)

    def test_deterministic(self):
        a = _webhook_id_for_entry("entry-123")
        b = _webhook_id_for_entry("entry-123")
        assert a == b

    def test_different_entries_differ(self):
        a = _webhook_id_for_entry("entry-aaa")
        b = _webhook_id_for_entry("entry-bbb")
        assert a != b


# ---------------------------------------------------------------------------
# webhook_url
# ---------------------------------------------------------------------------


class TestWebhookUrl:
    """Tests for webhook_url helper."""

    def test_returns_url_on_success(self):
        hass = MagicMock()
        url = webhook_url(hass, "entry-001")
        assert url is not None
        assert "webhook" in url

    def test_returns_none_on_exception(self):
        hass = MagicMock()
        from homeassistant.components import webhook as wh_mod

        original = wh_mod.async_generate_url
        wh_mod.async_generate_url = MagicMock(side_effect=RuntimeError("no external url"))
        try:
            url = webhook_url(hass, "entry-001")
            assert url is None
        finally:
            wh_mod.async_generate_url = original


# ---------------------------------------------------------------------------
# async_register_webhook / async_unregister_webhook
# ---------------------------------------------------------------------------


class TestRegisterUnregister:
    """Tests for webhook registration lifecycle."""

    @pytest.mark.asyncio
    async def test_register_returns_id(self):
        hass = MagicMock()
        wh_id = await async_register_webhook(hass, "entry-x")
        assert isinstance(wh_id, str)
        assert len(wh_id) == 32

    @pytest.mark.asyncio
    async def test_register_calls_ha_webhook(self):
        hass = MagicMock()
        from homeassistant.components import webhook as wh_mod

        wh_mod.async_register.reset_mock()
        await async_register_webhook(hass, "entry-x")
        wh_mod.async_register.assert_called_once()

    @pytest.mark.asyncio
    async def test_unregister_calls_ha_webhook(self):
        hass = MagicMock()
        from homeassistant.components import webhook as wh_mod

        wh_mod.async_unregister.reset_mock()
        await async_unregister_webhook(hass, "entry-x")
        wh_mod.async_unregister.assert_called_once()


# ---------------------------------------------------------------------------
# _async_handle_webhook — PING
# ---------------------------------------------------------------------------


class TestHandleWebhookPing:
    """Tests for PING lifecycle handling."""

    @pytest.mark.asyncio
    async def test_ping_returns_challenge(self):
        request = AsyncMock()
        request.json = AsyncMock(
            return_value={
                "lifecycle": "PING",
                "pingData": {"challenge": "test-challenge-123"},
            }
        )
        hass = MagicMock()
        resp = await _async_handle_webhook(hass, "wh-id", request)
        assert resp is not None
        assert resp.status == 200
        body = json.loads(resp.body)
        assert body["pingData"]["challenge"] == "test-challenge-123"

    @pytest.mark.asyncio
    async def test_ping_empty_challenge(self):
        request = AsyncMock()
        request.json = AsyncMock(
            return_value={
                "lifecycle": "PING",
                "pingData": {},
            }
        )
        hass = MagicMock()
        resp = await _async_handle_webhook(hass, "wh-id", request)
        assert resp is not None
        body = json.loads(resp.body)
        assert body["pingData"]["challenge"] == ""


# ---------------------------------------------------------------------------
# _async_handle_webhook — CONFIRMATION
# ---------------------------------------------------------------------------


class TestHandleWebhookConfirmation:
    """Tests for CONFIRMATION lifecycle handling."""

    @pytest.mark.asyncio
    async def test_confirmation_returns_200(self):
        request = AsyncMock()
        request.json = AsyncMock(
            return_value={
                "lifecycle": "CONFIRMATION",
                "confirmationData": {
                    "confirmationUrl": "https://api.smartthings.com/confirm/abc"
                },
            }
        )
        hass = MagicMock()
        mock_session = AsyncMock()
        with patch(
            "homeassistant.helpers.aiohttp_client.async_get_clientsession",
            return_value=mock_session,
        ):
            resp = await _async_handle_webhook(hass, "wh-id", request)
        assert resp is not None
        assert resp.status == 200


# ---------------------------------------------------------------------------
# _async_handle_webhook — EVENT
# ---------------------------------------------------------------------------


class TestHandleWebhookEvent:
    """Tests for EVENT lifecycle handling."""

    @pytest.mark.asyncio
    async def test_event_returns_200(self):
        request = AsyncMock()
        request.json = AsyncMock(
            return_value={
                "lifecycle": "EVENT",
                "eventData": {
                    "events": [
                        {
                            "eventType": "DEVICE_EVENT",
                            "deviceEvent": {
                                "deviceId": "dev-001",
                                "componentId": "main",
                                "capability": "switch",
                                "attribute": "switch",
                                "value": "off",
                            },
                        }
                    ]
                },
            }
        )
        hass = MagicMock()
        hass.data = {}
        resp = await _async_handle_webhook(hass, "wh-id", request)
        assert resp is not None
        assert resp.status == 200


# ---------------------------------------------------------------------------
# _async_handle_webhook — edge cases
# ---------------------------------------------------------------------------


class TestHandleWebhookEdgeCases:
    """Tests for edge cases in webhook handling."""

    @pytest.mark.asyncio
    async def test_invalid_json_returns_400(self):
        request = AsyncMock()
        request.json = AsyncMock(side_effect=ValueError("bad json"))
        hass = MagicMock()
        resp = await _async_handle_webhook(hass, "wh-id", request)
        assert resp is not None
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_unknown_lifecycle_returns_200(self):
        request = AsyncMock()
        request.json = AsyncMock(
            return_value={"lifecycle": "UNKNOWN_TYPE"}
        )
        hass = MagicMock()
        resp = await _async_handle_webhook(hass, "wh-id", request)
        assert resp is not None
        assert resp.status == 200

    @pytest.mark.asyncio
    async def test_missing_lifecycle_returns_200(self):
        request = AsyncMock()
        request.json = AsyncMock(return_value={})
        hass = MagicMock()
        resp = await _async_handle_webhook(hass, "wh-id", request)
        assert resp is not None
        assert resp.status == 200


# ---------------------------------------------------------------------------
# _process_device_events
# ---------------------------------------------------------------------------


class TestProcessDeviceEvents:
    """Tests for _process_device_events coordinator data patching."""

    def _make_coordinator(self, data: dict) -> MagicMock:
        coordinator = MagicMock()
        coordinator.data = data
        return coordinator

    def _make_runtime(self, coordinator: MagicMock) -> MagicMock:
        runtime = MagicMock()
        runtime.coordinator = coordinator
        return runtime

    def test_patches_existing_attribute(self):
        data = {
            "status": {
                "dev-001": {
                    "components": {
                        "main": {
                            "switch": {
                                "switch": {"value": "on"},
                            }
                        }
                    }
                }
            }
        }
        coordinator = self._make_coordinator(data)
        runtime = self._make_runtime(coordinator)
        hass = MagicMock()
        hass.data = {"smartthings_dynamic": {"entry1": runtime}}

        events = [
            {
                "eventType": "DEVICE_EVENT",
                "deviceEvent": {
                    "deviceId": "dev-001",
                    "componentId": "main",
                    "capability": "switch",
                    "attribute": "switch",
                    "value": "off",
                },
            }
        ]

        _process_device_events(hass, events)

        assert data["status"]["dev-001"]["components"]["main"]["switch"]["switch"]["value"] == "off"
        coordinator.async_set_updated_data.assert_called_once_with(data)

    def test_creates_new_attribute(self):
        data = {
            "status": {
                "dev-001": {
                    "components": {
                        "main": {
                            "switch": {
                                "switch": {"value": "on"},
                            }
                        }
                    }
                }
            }
        }
        coordinator = self._make_coordinator(data)
        runtime = self._make_runtime(coordinator)
        hass = MagicMock()
        hass.data = {"smartthings_dynamic": {"entry1": runtime}}

        events = [
            {
                "eventType": "DEVICE_EVENT",
                "deviceEvent": {
                    "deviceId": "dev-001",
                    "componentId": "main",
                    "capability": "switch",
                    "attribute": "energySavingStatus",
                    "value": "active",
                },
            }
        ]

        _process_device_events(hass, events)

        assert data["status"]["dev-001"]["components"]["main"]["switch"]["energySavingStatus"] == {"value": "active"}

    def test_creates_new_capability_and_component(self):
        data = {
            "status": {
                "dev-001": {
                    "components": {}
                }
            }
        }
        coordinator = self._make_coordinator(data)
        runtime = self._make_runtime(coordinator)
        hass = MagicMock()
        hass.data = {"smartthings_dynamic": {"entry1": runtime}}

        events = [
            {
                "eventType": "DEVICE_EVENT",
                "deviceEvent": {
                    "deviceId": "dev-001",
                    "componentId": "sub",
                    "capability": "temperatureMeasurement",
                    "attribute": "temperature",
                    "value": 22.5,
                },
            }
        ]

        _process_device_events(hass, events)

        temp = data["status"]["dev-001"]["components"]["sub"]["temperatureMeasurement"]["temperature"]
        assert temp == {"value": 22.5}

    def test_ignores_unknown_device(self):
        data = {
            "status": {
                "dev-001": {"components": {"main": {}}}
            }
        }
        coordinator = self._make_coordinator(data)
        runtime = self._make_runtime(coordinator)
        hass = MagicMock()
        hass.data = {"smartthings_dynamic": {"entry1": runtime}}

        events = [
            {
                "eventType": "DEVICE_EVENT",
                "deviceEvent": {
                    "deviceId": "dev-999",
                    "componentId": "main",
                    "capability": "switch",
                    "attribute": "switch",
                    "value": "on",
                },
            }
        ]

        _process_device_events(hass, events)

        # No crash, coordinator not notified
        coordinator.async_set_updated_data.assert_not_called()

    def test_ignores_non_device_events(self):
        data = {
            "status": {
                "dev-001": {"components": {"main": {}}}
            }
        }
        coordinator = self._make_coordinator(data)
        runtime = self._make_runtime(coordinator)
        hass = MagicMock()
        hass.data = {"smartthings_dynamic": {"entry1": runtime}}

        events = [
            {
                "eventType": "MODE_EVENT",
                "modeEvent": {"modeId": "mode-1"},
            }
        ]

        _process_device_events(hass, events)
        coordinator.async_set_updated_data.assert_not_called()

    def test_no_coordinators_no_crash(self):
        hass = MagicMock()
        hass.data = {}
        # Should not raise
        _process_device_events(hass, [])

    def test_coordinator_with_none_data(self):
        coordinator = self._make_coordinator(None)
        runtime = self._make_runtime(coordinator)
        hass = MagicMock()
        hass.data = {"smartthings_dynamic": {"entry1": runtime}}

        events = [
            {
                "eventType": "DEVICE_EVENT",
                "deviceEvent": {
                    "deviceId": "dev-001",
                    "componentId": "main",
                    "capability": "switch",
                    "attribute": "switch",
                    "value": "on",
                },
            }
        ]

        # Should not raise
        _process_device_events(hass, events)
        coordinator.async_set_updated_data.assert_not_called()

    def test_multiple_events_same_device(self):
        data = {
            "status": {
                "dev-001": {
                    "components": {
                        "main": {
                            "switch": {"switch": {"value": "on"}},
                            "temperatureMeasurement": {"temperature": {"value": 20}},
                        }
                    }
                }
            }
        }
        coordinator = self._make_coordinator(data)
        runtime = self._make_runtime(coordinator)
        hass = MagicMock()
        hass.data = {"smartthings_dynamic": {"entry1": runtime}}

        events = [
            {
                "eventType": "DEVICE_EVENT",
                "deviceEvent": {
                    "deviceId": "dev-001",
                    "componentId": "main",
                    "capability": "switch",
                    "attribute": "switch",
                    "value": "off",
                },
            },
            {
                "eventType": "DEVICE_EVENT",
                "deviceEvent": {
                    "deviceId": "dev-001",
                    "componentId": "main",
                    "capability": "temperatureMeasurement",
                    "attribute": "temperature",
                    "value": 25,
                },
            },
        ]

        _process_device_events(hass, events)

        assert data["status"]["dev-001"]["components"]["main"]["switch"]["switch"]["value"] == "off"
        assert data["status"]["dev-001"]["components"]["main"]["temperatureMeasurement"]["temperature"]["value"] == 25
        coordinator.async_set_updated_data.assert_called_once()

    def test_event_missing_required_fields_skipped(self):
        data = {
            "status": {
                "dev-001": {"components": {"main": {}}}
            }
        }
        coordinator = self._make_coordinator(data)
        runtime = self._make_runtime(coordinator)
        hass = MagicMock()
        hass.data = {"smartthings_dynamic": {"entry1": runtime}}

        events = [
            {
                "eventType": "DEVICE_EVENT",
                "deviceEvent": {
                    "deviceId": "dev-001",
                    # missing capability and attribute
                },
            }
        ]

        _process_device_events(hass, events)
        coordinator.async_set_updated_data.assert_not_called()
