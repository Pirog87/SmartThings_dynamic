"""Webhook handler for SmartThings real-time device events.

SmartThings SmartApp webhooks send lifecycle events (PING, CONFIRMATION,
EVENT) as POST requests.  This module registers a Home Assistant webhook
endpoint and processes those events, pushing device-state updates into the
coordinator so entities refresh instantly.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from aiohttp import web
from homeassistant.components import webhook
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def _webhook_id_for_entry(entry_id: str) -> str:
    """Deterministic webhook id derived from the config entry id."""
    raw = f"{DOMAIN}_{entry_id}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def webhook_url(hass: HomeAssistant, entry_id: str) -> str | None:
    """Return the full external webhook URL, or *None* if unavailable."""
    wh_id = _webhook_id_for_entry(entry_id)
    try:
        return webhook.async_generate_url(hass, wh_id)
    except Exception:  # noqa: BLE001
        return None


async def async_register_webhook(
    hass: HomeAssistant,
    entry_id: str,
) -> str:
    """Register the webhook in HA and return its id."""
    wh_id = _webhook_id_for_entry(entry_id)

    webhook.async_register(
        hass,
        DOMAIN,
        "SmartThings Dynamic",
        wh_id,
        _async_handle_webhook,
    )
    _LOGGER.debug("Registered webhook %s for entry %s", wh_id, entry_id)
    return wh_id


async def async_unregister_webhook(
    hass: HomeAssistant,
    entry_id: str,
) -> None:
    """Unregister the webhook (safe to call even if not registered)."""
    wh_id = _webhook_id_for_entry(entry_id)
    try:
        webhook.async_unregister(hass, wh_id)
        _LOGGER.debug("Unregistered webhook %s", wh_id)
    except KeyError:
        pass  # webhook was never registered (no external URL)


# ── Incoming event handler ──────────────────────────────────────────────────


async def _async_handle_webhook(
    hass: HomeAssistant,
    webhook_id: str,
    request: web.Request,
) -> web.Response | None:
    """Process a SmartThings SmartApp lifecycle POST."""
    try:
        data: dict[str, Any] = await request.json()
    except (ValueError, TypeError):
        _LOGGER.warning("Webhook received non-JSON payload")
        return web.Response(status=400)

    lifecycle = data.get("lifecycle", "").upper()

    # ── PING ────────────────────────────────────────────────────────────
    if lifecycle == "PING":
        challenge = data.get("pingData", {}).get("challenge", "")
        _LOGGER.debug("Webhook PING received, responding with challenge")
        return web.json_response({"pingData": {"challenge": challenge}})

    # ── CONFIRMATION ────────────────────────────────────────────────────
    if lifecycle == "CONFIRMATION":
        confirm_url = data.get("confirmationData", {}).get("confirmationUrl")
        if confirm_url:
            _LOGGER.info(
                "SmartThings CONFIRMATION received. Visit this URL to confirm: %s",
                confirm_url,
            )
            # Attempt automatic confirmation
            try:
                from homeassistant.helpers import aiohttp_client

                session = aiohttp_client.async_get_clientsession(hass)
                await session.get(confirm_url)
                _LOGGER.info("SmartApp automatically confirmed")
            except Exception:  # noqa: BLE001
                _LOGGER.warning(
                    "Could not auto-confirm SmartApp. Open this URL manually: %s",
                    confirm_url,
                )
        return web.Response(status=200)

    # ── EVENT ───────────────────────────────────────────────────────────
    if lifecycle == "EVENT":
        events = data.get("eventData", {}).get("events", [])
        _process_device_events(hass, events)
        return web.Response(status=200)

    # ── Unknown lifecycle ───────────────────────────────────────────────
    _LOGGER.debug("Webhook received unknown lifecycle: %s", lifecycle)
    return web.Response(status=200)


def _process_device_events(hass: HomeAssistant, events: list[dict[str, Any]]) -> None:
    """Push SmartThings device events into the coordinator data."""
    from .coordinator import SmartThingsDynamicCoordinator

    # Collect all coordinators
    coordinators: list[SmartThingsDynamicCoordinator] = []
    for runtime in hass.data.get(DOMAIN, {}).values():
        if hasattr(runtime, "coordinator"):
            coordinators.append(runtime.coordinator)

    if not coordinators:
        return

    updated_coordinators: set[int] = set()

    for event in events:
        if event.get("eventType") != "DEVICE_EVENT":
            continue

        dev_event = event.get("deviceEvent", {})
        device_id = dev_event.get("deviceId")
        component_id = dev_event.get("componentId", "main")
        capability = dev_event.get("capability")
        attribute = dev_event.get("attribute")
        value = dev_event.get("value")

        if not all((device_id, capability, attribute)):
            continue

        _LOGGER.debug(
            "Webhook event: %s/%s/%s/%s = %s",
            device_id,
            component_id,
            capability,
            attribute,
            value,
        )

        # Patch each coordinator that tracks this device
        for coordinator in coordinators:
            if coordinator.data is None:
                continue
            statuses = coordinator.data.get("status", {})
            if device_id not in statuses:
                continue

            # Navigate / create nested dicts
            components = statuses[device_id].setdefault("components", {})
            comp = components.setdefault(component_id, {})
            cap = comp.setdefault(capability, {})

            # Update the attribute payload in-place
            if attribute in cap and isinstance(cap[attribute], dict):
                cap[attribute]["value"] = value
            else:
                cap[attribute] = {"value": value}

            updated_coordinators.add(id(coordinator))

    # Notify listeners (triggers entity state refresh)
    for coordinator in coordinators:
        if id(coordinator) in updated_coordinators:
            coordinator.async_set_updated_data(coordinator.data)
