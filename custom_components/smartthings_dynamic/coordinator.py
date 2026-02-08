"""DataUpdateCoordinator for SmartThings Dynamic with Adaptive Polling."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from aiohttp import ClientError, ClientResponseError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SmartThingsApi
from .const import (
    ACTIVE_SCAN_INTERVAL,
    CONF_DEVICE_IDS,
    CONF_MAX_CONCURRENT_REQUESTS,
    CONF_SCAN_INTERVAL,
    DEFAULT_MAX_CONCURRENT_REQUESTS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

# Keywords indicating that the appliance is working and requires frequent updates.
ACTIVE_STATES: set[str] = {
    "run", "running", "printing",
    "heating", "cooking", "preheat", "preheating",
    "spinning", "drying", "rinsing", "washing",
    "cleaning", "partially_open", "opening", "closing",
    "busy", "thawing"
}

class SmartThingsDynamicCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that polls SmartThings for devices + status."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: SmartThingsApi,
        *,
        scan_interval: timedelta | None = None,
        max_concurrent_requests: int | None = None,
        device_ids: list[str] | None = None,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=scan_interval or DEFAULT_SCAN_INTERVAL,
        )
        self.api = api
        self._sem = asyncio.Semaphore(max_concurrent_requests or DEFAULT_MAX_CONCURRENT_REQUESTS)
        self._failed_devices: set[str] = set()
        # Empty list means "all devices" (backward compat).
        self._device_filter: set[str] = set(device_ids) if device_ids else set()

        # Remember the user-configured base interval
        self._configured_interval = scan_interval or DEFAULT_SCAN_INTERVAL

    @classmethod
    def from_entry(cls, hass: HomeAssistant, api: SmartThingsApi, entry) -> SmartThingsDynamicCoordinator:
        opts = entry.options
        data = entry.data
        scan = timedelta(seconds=int(opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL.total_seconds())))
        maxc = int(opts.get(CONF_MAX_CONCURRENT_REQUESTS, DEFAULT_MAX_CONCURRENT_REQUESTS))
        device_ids = opts.get(CONF_DEVICE_IDS) or data.get(CONF_DEVICE_IDS) or []
        return cls(hass, api, scan_interval=scan, max_concurrent_requests=maxc, device_ids=device_ids)

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            # 1. Fetch devices list (lightweight)
            devices_payload = await self.api.async_list_devices()
            items = devices_payload.get("items", [])
            all_devices = {d["deviceId"]: d for d in items if isinstance(d, dict) and "deviceId" in d}

            # 2. Filter to selected devices (empty filter = all)
            if self._device_filter:
                devices = {did: d for did, d in all_devices.items() if did in self._device_filter}
            else:
                devices = all_devices

            statuses: dict[str, Any] = {}
            current_failed: set[str] = set()

            # Flag to determine if we need fast polling
            any_device_active = False

            async def _fetch_status(device_id: str) -> None:
                nonlocal any_device_active
                async with self._sem:
                    try:
                        st = await self.api.async_get_device_status(device_id)

                        # --- FIX: SANITIZE DATA FROM API ---
                        # API can sometimes return a string (error msg) instead of dict.
                        # We must ensure only dicts are stored to prevent crashes downstream.
                        if isinstance(st, dict):
                            statuses[device_id] = st
                            self._failed_devices.discard(device_id)

                            # Check for activity only if valid dict
                            if not any_device_active:
                                for comp in st.get("components", {}).values():
                                    for cap in comp.values():
                                        for attr_val in cap.values():
                                            if isinstance(attr_val, dict):
                                                val = attr_val.get("value")
                                                if isinstance(val, str) and val.lower() in ACTIVE_STATES:
                                                    any_device_active = True
                                                    return
                        else:
                            # Log debug and store safe empty fallback
                            _LOGGER.debug("Device %s returned invalid status type: %s", device_id, type(st))
                            statuses[device_id] = {"components": {}}
                            # We don't mark it as failed_device to avoid constant retries/logs if it's just weird data

                    except Exception as err:
                        current_failed.add(device_id)
                        if device_id not in self._failed_devices:
                            _LOGGER.warning(
                                "Failed to fetch status for device %s: %s",
                                devices.get(device_id, {}).get("label", device_id),
                                err
                            )
                        statuses[device_id] = {"components": {}}

            # Execute requests in parallel
            await asyncio.gather(
                *(_fetch_status(did) for did in devices),
                return_exceptions=True
            )

            self._failed_devices = current_failed

            # --- ADJUST POLLING INTERVAL ---
            if any_device_active:
                if self.update_interval != ACTIVE_SCAN_INTERVAL:
                    _LOGGER.debug("Device activity detected. Switching to FAST polling (%s)", ACTIVE_SCAN_INTERVAL)
                    self.update_interval = ACTIVE_SCAN_INTERVAL
            else:
                if self.update_interval != self._configured_interval:
                    _LOGGER.debug("No activity. Switching back to NORMAL polling (%s)", self._configured_interval)
                    self.update_interval = self._configured_interval

            return {"devices": devices, "status": statuses}

        except (TimeoutError, ClientError, ClientResponseError) as err:
            raise UpdateFailed(f"Error communicating with SmartThings: {err}") from err
