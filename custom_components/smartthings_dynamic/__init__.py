"""SmartThings Dynamic integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

# Pre-load platform modules at import time.
# Home Assistant imports the integration in the import executor by default, but may import platform
# modules later during config entry setup. Pre-loading reduces (and in newer HA versions can avoid)
# "Detected blocking call to import_module inside the event loop" warnings.
from . import binary_sensor as _binary_sensor  # noqa: F401
from . import button as _button  # noqa: F401
from . import camera as _camera  # noqa: F401
from . import number as _number  # noqa: F401
from . import select as _select  # noqa: F401
from . import sensor as _sensor  # noqa: F401
from . import switch as _switch  # noqa: F401
from . import vacuum as _vacuum  # noqa: F401
from .api import SmartThingsApi
from .const import DOMAIN, PLATFORMS, WEBHOOK_BACKUP_POLL_INTERVAL
from .coordinator import SmartThingsDynamicCoordinator
from .webhook import async_register_webhook, async_unregister_webhook, webhook_url

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class SmartThingsDynamicRuntimeData:
    """Runtime data for a config entry."""

    api: SmartThingsApi
    coordinator: SmartThingsDynamicCoordinator


SERVICE_SEND_COMMAND = "send_command"

SERVICE_SCHEMA_SEND_COMMAND = vol.Schema(
    {
        vol.Required("device_id"): cv.string,
        vol.Optional("component", default="main"): cv.string,
        vol.Required("capability"): cv.string,
        vol.Required("command"): cv.string,
        vol.Optional("arguments", default=[]): list,
        vol.Optional("config_entry_id"): cv.string,
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration (YAML not used, but keep for HA)."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SmartThings Dynamic from a config entry."""
    implementation = await config_entry_oauth2_flow.async_get_config_entry_implementation(hass, entry)
    oauth_session = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)
    api = SmartThingsApi(oauth_session)

    coordinator = SmartThingsDynamicCoordinator.from_entry(hass, api, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = SmartThingsDynamicRuntimeData(api=api, coordinator=coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # --- Webhook for real-time updates (auto-detect) ---
    wh_url = webhook_url(hass, entry.entry_id)
    if wh_url:
        await async_register_webhook(hass, entry.entry_id)
        _LOGGER.info(
            "External URL detected – webhook active at %s, polling reduced to %s",
            wh_url, WEBHOOK_BACKUP_POLL_INTERVAL,
        )
        coordinator.update_interval = WEBHOOK_BACKUP_POLL_INTERVAL
    else:
        _LOGGER.info("No external URL configured – using polling only (interval %s)", coordinator.update_interval)

    # Reload when options change
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    _async_register_services(hass)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Unregister webhook (no-op if not registered)
    await async_unregister_webhook(hass, entry.entry_id)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


def _async_register_services(hass: HomeAssistant) -> None:
    """Register domain services once."""
    if hass.services.has_service(DOMAIN, SERVICE_SEND_COMMAND):
        return

    async def _handle_send_command(call: ServiceCall) -> None:
        data = SERVICE_SCHEMA_SEND_COMMAND(dict(call.data))
        entry_id = data.get("config_entry_id")

        runtimes = {
            k: v for k, v in hass.data.get(DOMAIN, {}).items() if isinstance(v, SmartThingsDynamicRuntimeData)
        }

        runtime: SmartThingsDynamicRuntimeData | None = None
        if entry_id:
            runtime = runtimes.get(entry_id)
        elif len(runtimes) == 1:
            runtime = next(iter(runtimes.values()))

        if runtime is None:
            raise HomeAssistantError(
                "Nie mogę wybrać instancji integracji. Podaj config_entry_id albo zostaw tylko jedną instancję."
            )

        await runtime.api.async_execute_command(
            device_id=data["device_id"],
            component=data["component"],
            capability=data["capability"],
            command=data["command"],
            arguments=data.get("arguments") or [],
        )

    hass.services.async_register(DOMAIN, SERVICE_SEND_COMMAND, _handle_send_command, schema=SERVICE_SCHEMA_SEND_COMMAND)
