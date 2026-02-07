"""Camera platform for SmartThings Dynamic (imageCapture etc.)."""

from __future__ import annotations

import logging
from typing import Any

from aiohttp import ClientError

from homeassistant.components.camera import Camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN
from .entity import EntityRef, SmartThingsDynamicBaseEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator = runtime.coordinator

    added: set[str] = set()

    @callback
    def _async_discover() -> None:
        data = coordinator.data or {}
        devices: dict[str, Any] = data.get("devices") or {}
        statuses: dict[str, Any] = data.get("status") or {}

        new_entities: list[SmartThingsDynamicCamera] = []

        for device_id, dev_status in statuses.items():
            device = devices.get(device_id)
            if not device or not isinstance(dev_status, dict):
                continue

            comps = dev_status.get("components") or {}
            for comp_id, comp_status in comps.items():
                if not isinstance(comp_status, dict):
                    continue
                for cap_id, cap_status in comp_status.items():
                    if not isinstance(cap_status, dict):
                        continue
                    # Common pattern: imageCapture.image
                    payload = cap_status.get("image")
                    if not isinstance(payload, dict):
                        continue
                    url = payload.get("value")
                    if not isinstance(url, str) or not url.startswith("http"):
                        continue

                    key = f"{device_id}|{comp_id}|{cap_id}|image"
                    if key in added:
                        continue
                    added.add(key)

                    suffix = f"{cap_id.split('.')[-1]}.image"
                    new_entities.append(
                        SmartThingsDynamicCamera(
                            coordinator,
                            hass,
                            entry_id=entry.entry_id,
                            device=device,
                            ref=EntityRef(
                                device_id=device_id,
                                component_id=comp_id,
                                capability_id=cap_id,
                                attribute="image",
                            ),
                            name_suffix=suffix,
                        )
                    )

        if new_entities:
            _LOGGER.debug("Adding %d SmartThings Dynamic camera entities", len(new_entities))
            async_add_entities(new_entities)

    _async_discover()
    coordinator.async_add_listener(_async_discover)


class SmartThingsDynamicCamera(SmartThingsDynamicBaseEntity, Camera):
    """Camera entity that fetches the image URL reported by SmartThings."""

    def __init__(
        self,
        coordinator,
        hass: HomeAssistant,
        *,
        entry_id: str,
        device: dict[str, Any],
        ref: EntityRef,
        name_suffix: str | None = None,
    ) -> None:
        Camera.__init__(self)
        SmartThingsDynamicBaseEntity.__init__(self, coordinator, entry_id=entry_id, device=device, ref=ref, name_suffix=name_suffix)
        self.hass = hass

    async def async_camera_image(self, width: int | None = None, height: int | None = None) -> bytes | None:
        url = self._attr_value()
        if not isinstance(url, str) or not url.startswith("http"):
            return None

        session = async_get_clientsession(self.hass)
        try:
            resp = await session.get(url)
            resp.raise_for_status()
            return await resp.read()
        except ClientError as err:
            _LOGGER.debug("Failed to fetch SmartThings camera image: %s", err)
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "image_url": self._attr_value(),
            "device_id": self.ref.device_id,
            "component": self.ref.component_id,
            "capability": self.ref.capability_id,
        }
