"""Tests for automatic device discovery and coordinator device filtering."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.smartthings_dynamic.config_flow import _device_label
from custom_components.smartthings_dynamic.coordinator import SmartThingsDynamicCoordinator

# ─── _device_label helper ──────────────────────────────────────────────────


class TestDeviceLabelConfigFlow:
    def test_label_with_model(self):
        device = {"label": "Samsung Washer", "modelName": "WF45R6100AW"}
        assert _device_label(device) == "Samsung Washer (WF45R6100AW)"

    def test_label_without_model(self):
        device = {"label": "My Vacuum"}
        assert _device_label(device) == "My Vacuum"

    def test_name_fallback(self):
        device = {"name": "Oven", "deviceTypeName": "OCF Device"}
        assert _device_label(device) == "Oven (OCF Device)"

    def test_device_id_fallback(self):
        device = {"deviceId": "abc-123"}
        assert _device_label(device) == "abc-123"

    def test_empty_device(self):
        assert _device_label({}) == "?"


# ─── Coordinator device filtering ──────────────────────────────────────────


class TestCoordinatorDeviceFilter:
    @pytest.mark.asyncio
    async def test_no_filter_returns_all_devices(self):
        """When device_ids is empty, all devices are returned."""
        api = MagicMock()
        api.async_list_devices = AsyncMock(
            return_value={
                "items": [
                    {"deviceId": "d1", "label": "Device 1"},
                    {"deviceId": "d2", "label": "Device 2"},
                    {"deviceId": "d3", "label": "Device 3"},
                ]
            }
        )
        api.async_get_device_status = AsyncMock(return_value={"components": {}})

        hass = MagicMock()
        coordinator = SmartThingsDynamicCoordinator(hass, api, device_ids=[])

        result = await coordinator._async_update_data()

        assert set(result["devices"].keys()) == {"d1", "d2", "d3"}

    @pytest.mark.asyncio
    async def test_filter_returns_only_selected(self):
        """When device_ids is set, only matching devices are included."""
        api = MagicMock()
        api.async_list_devices = AsyncMock(
            return_value={
                "items": [
                    {"deviceId": "d1", "label": "Device 1"},
                    {"deviceId": "d2", "label": "Device 2"},
                    {"deviceId": "d3", "label": "Device 3"},
                ]
            }
        )
        api.async_get_device_status = AsyncMock(return_value={"components": {}})

        hass = MagicMock()
        coordinator = SmartThingsDynamicCoordinator(hass, api, device_ids=["d1", "d3"])

        result = await coordinator._async_update_data()

        assert set(result["devices"].keys()) == {"d1", "d3"}
        assert "d2" not in result["devices"]

    @pytest.mark.asyncio
    async def test_filter_skips_unknown_ids(self):
        """Device IDs in filter but not from API are silently ignored."""
        api = MagicMock()
        api.async_list_devices = AsyncMock(
            return_value={
                "items": [
                    {"deviceId": "d1", "label": "Device 1"},
                ]
            }
        )
        api.async_get_device_status = AsyncMock(return_value={"components": {}})

        hass = MagicMock()
        coordinator = SmartThingsDynamicCoordinator(
            hass, api, device_ids=["d1", "nonexistent"]
        )

        result = await coordinator._async_update_data()

        assert set(result["devices"].keys()) == {"d1"}

    @pytest.mark.asyncio
    async def test_filter_only_polls_selected_devices(self):
        """Status requests are only sent for filtered devices."""
        api = MagicMock()
        api.async_list_devices = AsyncMock(
            return_value={
                "items": [
                    {"deviceId": "d1", "label": "Device 1"},
                    {"deviceId": "d2", "label": "Device 2"},
                    {"deviceId": "d3", "label": "Device 3"},
                ]
            }
        )
        api.async_get_device_status = AsyncMock(return_value={"components": {}})

        hass = MagicMock()
        coordinator = SmartThingsDynamicCoordinator(hass, api, device_ids=["d2"])

        await coordinator._async_update_data()

        # Only d2 should have been polled for status
        api.async_get_device_status.assert_called_once_with("d2")

    @pytest.mark.asyncio
    async def test_none_device_ids_returns_all(self):
        """device_ids=None behaves same as empty (all devices)."""
        api = MagicMock()
        api.async_list_devices = AsyncMock(
            return_value={
                "items": [
                    {"deviceId": "d1", "label": "Device 1"},
                    {"deviceId": "d2", "label": "Device 2"},
                ]
            }
        )
        api.async_get_device_status = AsyncMock(return_value={"components": {}})

        hass = MagicMock()
        coordinator = SmartThingsDynamicCoordinator(hass, api, device_ids=None)

        result = await coordinator._async_update_data()

        assert set(result["devices"].keys()) == {"d1", "d2"}


# ─── Coordinator.from_entry reads device_ids ───────────────────────────────


class TestFromEntry:
    def test_reads_device_ids_from_options(self):
        """Options take precedence over data for device_ids."""
        hass = MagicMock()
        api = MagicMock()
        entry = MagicMock()
        entry.options = {"device_ids": ["d1", "d2"]}
        entry.data = {"device_ids": ["d1"]}

        coordinator = SmartThingsDynamicCoordinator.from_entry(hass, api, entry)

        assert coordinator._device_filter == {"d1", "d2"}

    def test_falls_back_to_data(self):
        """If options has no device_ids, falls back to data."""
        hass = MagicMock()
        api = MagicMock()
        entry = MagicMock()
        entry.options = {}
        entry.data = {"device_ids": ["d3"]}

        coordinator = SmartThingsDynamicCoordinator.from_entry(hass, api, entry)

        assert coordinator._device_filter == {"d3"}

    def test_empty_device_ids_means_all(self):
        """Empty list results in empty filter (= all devices)."""
        hass = MagicMock()
        api = MagicMock()
        entry = MagicMock()
        entry.options = {}
        entry.data = {}

        coordinator = SmartThingsDynamicCoordinator.from_entry(hass, api, entry)

        assert coordinator._device_filter == set()
