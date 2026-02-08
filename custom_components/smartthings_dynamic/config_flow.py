"""Config flow for SmartThings Dynamic."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_AGGRESSIVE_MODE,
    CONF_DEVICE_IDS,
    CONF_EXPOSE_COMMAND_BUTTONS,
    CONF_EXPOSE_RAW_SENSORS,
    CONF_INCLUDE_CONTROL_ATTRIBUTES_AS_SENSORS,
    CONF_MAX_CONCURRENT_REQUESTS,
    CONF_SCAN_INTERVAL,
    DEFAULT_AGGRESSIVE_MODE,
    DEFAULT_MAX_CONCURRENT_REQUESTS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    OAUTH2_SCOPES,
    SMARTTHINGS_API_BASE,
)

_LOGGER = logging.getLogger(__name__)


def _device_label(device: dict[str, Any]) -> str:
    """Build a human-readable label for a device."""
    label = device.get("label") or device.get("name") or device.get("deviceId", "?")
    model = device.get("deviceTypeName") or device.get("modelName") or ""
    if model:
        return f"{label} ({model})"
    return str(label)


class SmartThingsDynamicConfigFlow(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN
):
    """Handle a config flow for SmartThings Dynamic."""

    DOMAIN = DOMAIN
    VERSION = 1

    def __init__(self) -> None:
        super().__init__()
        self._oauth_data: dict[str, Any] = {}
        self._location_id: str | None = None
        self._discovered_devices: dict[str, str] = {}  # device_id → label

    @property
    def logger(self) -> logging.Logger:
        return _LOGGER

    @property
    def extra_authorize_data(self) -> dict:
        return {"scope": " ".join(OAUTH2_SCOPES)}

    async def async_oauth_create_entry(
        self, data: dict[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Validate token, discover devices, then show selection step."""
        token = data["token"]

        try:
            async with asyncio.timeout(30):
                resp = await config_entry_oauth2_flow.async_oauth2_request(
                    self.hass,
                    token,
                    "get",
                    f"{SMARTTHINGS_API_BASE}/devices",
                )
                resp.raise_for_status()
                devices_payload = await resp.json()
        except TimeoutError:
            return self.async_abort(reason="timeout")
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("SmartThings token validation failed: %s", err)
            return self.async_abort(reason="cannot_connect")

        # Extract location_id for unique_id
        self._location_id = None
        items = (
            devices_payload.get("items")
            if isinstance(devices_payload, dict)
            else None
        )
        if items and isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and item.get("locationId"):
                    self._location_id = item["locationId"]
                    break

        if self._location_id:
            await self.async_set_unique_id(str(self._location_id))
            self._abort_if_unique_id_configured()

        # Build device map for selection
        self._oauth_data = data
        self._discovered_devices = {}
        for item in items or []:
            if isinstance(item, dict) and "deviceId" in item:
                self._discovered_devices[item["deviceId"]] = _device_label(item)

        # If no devices found, create entry immediately (nothing to select)
        if not self._discovered_devices:
            return self.async_create_entry(
                title="SmartThings Dynamic",
                data={**self._oauth_data, "location_id": self._location_id, CONF_DEVICE_IDS: []},
            )

        return await self.async_step_select_devices()

    async def async_step_select_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Let the user pick which devices to monitor."""
        if user_input is not None:
            selected = user_input.get(CONF_DEVICE_IDS, [])
            return self.async_create_entry(
                title="SmartThings Dynamic",
                data={
                    **self._oauth_data,
                    "location_id": self._location_id,
                    CONF_DEVICE_IDS: selected,
                },
            )

        # Default: all devices selected
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_DEVICE_IDS,
                    default=list(self._discovered_devices.keys()),
                ): cv.multi_select(self._discovered_devices),
            }
        )
        return self.async_show_form(step_id="select_devices", data_schema=schema)

    @staticmethod
    @config_entries.callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return SmartThingsDynamicOptionsFlow(config_entry)


class SmartThingsDynamicOptionsFlow(config_entries.OptionsFlow):
    """Options flow for SmartThings Dynamic."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    def _get_device_options(self) -> dict[str, str]:
        """Return {device_id: label} from the running coordinator data."""
        from .helpers import device_label as _dev_label

        runtime = self.hass.data.get(DOMAIN, {}).get(self._config_entry.entry_id)
        if not runtime:
            return {}
        data = runtime.coordinator.data or {}
        devices: dict[str, Any] = data.get("devices") or {}
        return {
            dev_id: _dev_label(dev)
            for dev_id, dev in devices.items()
        }

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        opts = self._config_entry.options
        entry_data = self._config_entry.data

        # Build device multi-select from coordinator data
        device_options = self._get_device_options()
        current_device_ids = (
            opts.get(CONF_DEVICE_IDS)
            or entry_data.get(CONF_DEVICE_IDS)
            or list(device_options.keys())
        )

        schema_fields: dict[Any, Any] = {}

        if device_options:
            schema_fields[
                vol.Optional(CONF_DEVICE_IDS, default=current_device_ids)
            ] = cv.multi_select(device_options)

        schema_fields.update(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=int(
                        opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL.total_seconds())
                    ),
                ): vol.Coerce(int),
                vol.Optional(
                    CONF_MAX_CONCURRENT_REQUESTS,
                    default=int(
                        opts.get(CONF_MAX_CONCURRENT_REQUESTS, DEFAULT_MAX_CONCURRENT_REQUESTS)
                    ),
                ): vol.Coerce(int),
                vol.Optional(
                    CONF_EXPOSE_COMMAND_BUTTONS,
                    default=bool(opts.get(CONF_EXPOSE_COMMAND_BUTTONS, True)),
                ): bool,
                vol.Optional(
                    CONF_EXPOSE_RAW_SENSORS,
                    default=bool(opts.get(CONF_EXPOSE_RAW_SENSORS, False)),
                ): bool,
                vol.Optional(
                    CONF_INCLUDE_CONTROL_ATTRIBUTES_AS_SENSORS,
                    default=bool(
                        opts.get(CONF_INCLUDE_CONTROL_ATTRIBUTES_AS_SENSORS, False)
                    ),
                ): bool,
                vol.Optional(
                    CONF_AGGRESSIVE_MODE,
                    default=bool(opts.get(CONF_AGGRESSIVE_MODE, DEFAULT_AGGRESSIVE_MODE)),
                ): bool,
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema_fields),
        )
