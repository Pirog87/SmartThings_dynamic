"""Config flow for SmartThings Dynamic."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import config_entry_oauth2_flow

from .const import (
    CONF_EXPOSE_COMMAND_BUTTONS,
    CONF_EXPOSE_RAW_SENSORS,
    CONF_INCLUDE_CONTROL_ATTRIBUTES_AS_SENSORS,
    CONF_AGGRESSIVE_MODE,
    CONF_MAX_CONCURRENT_REQUESTS,
    CONF_SCAN_INTERVAL,
    DOMAIN,
    OAUTH2_SCOPES,
    SMARTTHINGS_API_BASE,
    DEFAULT_MAX_CONCURRENT_REQUESTS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_AGGRESSIVE_MODE,
)

_LOGGER = logging.getLogger(__name__)


class SmartThingsDynamicConfigFlow(config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN):
    """Handle a config flow for SmartThings Dynamic."""

    DOMAIN = DOMAIN
    VERSION = 1

    @property
    def logger(self) -> logging.Logger:
        return _LOGGER

    @property
    def extra_authorize_data(self) -> dict:
        # Add scopes required by the integration.
        return {"scope": " ".join(OAUTH2_SCOPES)}

    async def async_oauth_create_entry(self, data: dict[str, Any]) -> config_entries.ConfigFlowResult:
        """Create the config entry after OAuth is done."""
        token = data["token"]

        # Validate token by calling /devices and use the locationId as a stable unique_id.
        try:
            async with asyncio.timeout(30):
                resp = await config_entry_oauth2_flow.async_oauth2_request(
                    self.hass,
                    token,
                    "get",
                    f"{SMARTTHINGS_API_BASE}/devices",
                )
                resp.raise_for_status()
                devices = await resp.json()
        except TimeoutError:
            return self.async_abort(reason="timeout")
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("SmartThings token validation failed: %s", err)
            return self.async_abort(reason="cannot_connect")

        location_id = None
        try:
            items = devices.get("items") if isinstance(devices, dict) else None
            if items and isinstance(items, list) and items and isinstance(items[0], dict):
                location_id = items[0].get("locationId")
        except Exception:  # noqa: BLE001
            location_id = None

        if location_id:
            await self.async_set_unique_id(str(location_id))
            self._abort_if_unique_id_configured()

        data = {**data, "location_id": location_id}

        return self.async_create_entry(title="SmartThings Dynamic", data=data)

    @staticmethod
    @config_entries.callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return SmartThingsDynamicOptionsFlow(config_entry)


class SmartThingsDynamicOptionsFlow(config_entries.OptionsFlow):
    """Options flow for SmartThings Dynamic."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        opts = self._config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=int(opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL.total_seconds())),
                ): vol.Coerce(int),
                vol.Optional(
                    CONF_MAX_CONCURRENT_REQUESTS,
                    default=int(opts.get(CONF_MAX_CONCURRENT_REQUESTS, DEFAULT_MAX_CONCURRENT_REQUESTS)),
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
                    default=bool(opts.get(CONF_INCLUDE_CONTROL_ATTRIBUTES_AS_SENSORS, False)),
                ): bool,
                vol.Optional(
                    CONF_AGGRESSIVE_MODE,
                    default=bool(opts.get(CONF_AGGRESSIVE_MODE, DEFAULT_AGGRESSIVE_MODE)),
                ): bool,
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
