"""Camera platform for SmartThings Dynamic.

Supports three camera types found in Samsung appliances:

1. **imageCapture** (standard) — oven cameras, robot vacuums with imageCapture.
   Sends the ``take`` command to trigger a new snapshot, then fetches the
   resulting image URL from the ``image`` attribute.

2. **samsungce.viewInside** — Samsung Family Hub refrigerator "View Inside"
   cameras.  The ``contents`` attribute holds an array of ``{fileId: ...}``
   objects.  Images are downloaded via an authenticated SmartThings UDO
   endpoint.

3. **videoCapture** — Samsung ovens with a cooking camera.  The ``clip``
   attribute describes the latest clip stored in the SmartThings cloud
   (``clipPath``, ``thumbnailPath``, ``status``, ``correlationId``).  The
   camera shows the clip thumbnail; no capture command is sent.

4. **Generic image URL** (fallback) — any capability that exposes an ``image``
   attribute whose value is an HTTP URL.  No ``take`` command is sent.

SmartThings media hosts (``*.st-av.net``) reject anonymous requests, so every
download goes through the integration's OAuth session first and falls back to
a plain request only for pre-signed URLs.  A refused media request never
triggers re-authentication of the config entry.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any
from urllib.parse import quote

from aiohttp import ClientError

from homeassistant.components.camera import Camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SmartThingsApi
from .const import CONF_VIEWINSIDE_CID, DOMAIN
from .entity import EntityRef, SmartThingsDynamicBaseEntity
from .helpers import get_capability_status

_LOGGER = logging.getLogger(__name__)

# Samsung custom capability for fridge internal cameras.
VIEW_INSIDE_CAP = "samsungce.viewInside"
# Standard SmartThings capability for still image capture.
IMAGE_CAPTURE_CAP = "imageCapture"
# Standard SmartThings capability for video clips (Samsung oven camera).
VIDEO_CAPTURE_CAP = "videoCapture"

# Keys of the ``videoCapture.clip`` object that may hold the thumbnail / clip URL.
_CLIP_THUMBNAIL_KEYS = ("thumbnailPath", "thumbnailUrl", "thumbnail", "imagePath", "image")
_CLIP_VIDEO_KEYS = ("clipPath", "clipUrl", "clip", "videoPath")

# SmartThings UDO endpoint for downloading fridge camera images.
VIEW_INSIDE_IMAGE_URL = "https://client.smartthings.com/udo/file_links/{file_id}"
# A fridge photo link expires about 10 minutes after the fridge publishes it;
# ``viewInside.refreshAll`` makes the fridge publish fresh links.  Ask at most
# this often, so a dashboard left open does not flood the fridge.
_VIEW_INSIDE_REFRESH_MIN_INTERVAL_S = 60.0


def view_inside_image_url(file_id: str, device_id: str | None = None, cid: str | None = None) -> str:
    """Build the download URL of one fridge photo.

    The endpoint is undocumented.  Community projects call it with the device
    id (``di``) and the Samsung app client id (``cid``); ``cid`` is only added
    when the user set it in the integration options.
    """
    url = VIEW_INSIDE_IMAGE_URL.format(file_id=quote(file_id, safe=""))
    params = [("di", device_id), ("cid", cid)]
    query = "&".join(f"{k}={quote(v, safe='')}" for k, v in params if v)
    return f"{url}?{query}" if query else url


def _parse_ts(value: Any) -> float | None:
    """Parse an ISO-8601 timestamp (``2026-11-10T11:50:16Z``) to epoch seconds."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None

# Delay after ``take`` to give the device time to upload the image.
_TAKE_DELAY_S = 2.0
# The frontend asks for a still image every ~10 s while a camera is on screen.
# Send ``take`` at most this often, so a dashboard does not flood the device.
_TAKE_MIN_INTERVAL_S = 60.0


async def async_download_media(hass: HomeAssistant, api: SmartThingsApi | None, url: str) -> bytes | None:
    """Download a SmartThings media file (camera image or clip thumbnail).

    Tries the authenticated OAuth session first (SmartThings media hosts need a
    Bearer token), then a plain request for pre-signed URLs.  Returns ``None``
    when both fail; errors are only logged.
    """
    if api is not None:
        try:
            return await api.async_fetch_media(url)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Authenticated media download failed for %s: %s", url, err)

    session = async_get_clientsession(hass)
    try:
        resp = await session.get(url)
        resp.raise_for_status()
        return await resp.read()
    except (ClientError, TimeoutError) as err:
        _LOGGER.debug("Plain media download failed for %s: %s", url, err)
        return None


def _first_url(obj: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    """Return the first HTTP URL found under ``keys`` in ``obj``."""
    for key in keys:
        val = obj.get(key)
        if isinstance(val, str) and val.startswith("http"):
            return val
    return None


class _MediaCacheMixin:
    """Keep the last downloaded image so the same URL is fetched only once."""

    _cache_url: str | None = None
    _cache_bytes: bytes | None = None

    async def _async_cached_download(self, hass: HomeAssistant, api: SmartThingsApi | None, url: str) -> bytes | None:
        if url == self._cache_url and self._cache_bytes:
            return self._cache_bytes
        data = await async_download_media(hass, api, url)
        if data:
            self._cache_url, self._cache_bytes = url, data
            return data
        # Keep showing the previous picture rather than a broken image.
        return self._cache_bytes


# ─── Platform setup ────────────────────────────────────────────────────────


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator = runtime.coordinator
    api: SmartThingsApi = runtime.api

    added: set[str] = set()

    @callback
    def _async_discover() -> None:
        data = coordinator.data or {}
        devices: dict[str, Any] = data.get("devices") or {}
        statuses: dict[str, Any] = data.get("status") or {}

        new_entities: list[Camera] = []

        for device_id, dev_status in statuses.items():
            device = devices.get(device_id)
            if not device or not isinstance(dev_status, dict):
                continue

            comps = dev_status.get("components") or {}
            for comp_id, comp_status in comps.items():
                if not isinstance(comp_status, dict):
                    continue

                # --- 1. samsungce.viewInside (fridge camera) ---
                if VIEW_INSIDE_CAP in comp_status:
                    key = f"{device_id}|{comp_id}|{VIEW_INSIDE_CAP}"
                    if key not in added:
                        vi_status = comp_status[VIEW_INSIDE_CAP]
                        if isinstance(vi_status, dict):
                            added.add(key)
                            new_entities.append(
                                SmartThingsViewInsideCamera(
                                    coordinator,
                                    api,
                                    hass,
                                    entry_id=entry.entry_id,
                                    device=device,
                                    ref=EntityRef(
                                        device_id=device_id,
                                        component_id=comp_id,
                                        capability_id=VIEW_INSIDE_CAP,
                                        attribute="contents",
                                    ),
                                    name_suffix="viewInside",
                                    cid=str(entry.options.get(CONF_VIEWINSIDE_CID) or "").strip() or None,
                                )
                            )

                # --- 2. imageCapture (oven, vacuum, generic cameras) ---
                if IMAGE_CAPTURE_CAP in comp_status:
                    key = f"{device_id}|{comp_id}|{IMAGE_CAPTURE_CAP}"
                    if key not in added:
                        ic_status = comp_status[IMAGE_CAPTURE_CAP]
                        if isinstance(ic_status, dict):
                            added.add(key)
                            new_entities.append(
                                SmartThingsImageCaptureCamera(
                                    coordinator,
                                    api,
                                    hass,
                                    entry_id=entry.entry_id,
                                    device=device,
                                    ref=EntityRef(
                                        device_id=device_id,
                                        component_id=comp_id,
                                        capability_id=IMAGE_CAPTURE_CAP,
                                        attribute="image",
                                    ),
                                    name_suffix="imageCapture",
                                )
                            )

                # --- 3. videoCapture (oven camera clips) ---
                # Only when the device has produced a clip object; robot vacuums
                # report the capability with ``clip: null`` and get no entity.
                vc_status = comp_status.get(VIDEO_CAPTURE_CAP)
                if isinstance(vc_status, dict):
                    clip_payload = vc_status.get("clip")
                    if isinstance(clip_payload, dict) and isinstance(clip_payload.get("value"), dict):
                        key = f"{device_id}|{comp_id}|{VIDEO_CAPTURE_CAP}"
                        if key not in added:
                            added.add(key)
                            new_entities.append(
                                SmartThingsVideoCaptureCamera(
                                    coordinator,
                                    api,
                                    hass,
                                    entry_id=entry.entry_id,
                                    device=device,
                                    ref=EntityRef(
                                        device_id=device_id,
                                        component_id=comp_id,
                                        capability_id=VIDEO_CAPTURE_CAP,
                                        attribute="clip",
                                    ),
                                    name_suffix="videoCapture",
                                )
                            )

                # --- 4. Fallback: any other capability with an image URL ---
                for cap_id, cap_status in comp_status.items():
                    if cap_id in (IMAGE_CAPTURE_CAP, VIEW_INSIDE_CAP, VIDEO_CAPTURE_CAP):
                        continue
                    if not isinstance(cap_status, dict):
                        continue
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
                        SmartThingsGenericCamera(
                            coordinator,
                            hass,
                            api=api,
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


# ─── imageCapture camera ───────────────────────────────────────────────────


class SmartThingsImageCaptureCamera(_MediaCacheMixin, SmartThingsDynamicBaseEntity, Camera):
    """Camera using the standard ``imageCapture`` capability.

    Sends the ``take`` command to request a fresh snapshot, waits briefly,
    then downloads the image from the URL in the ``image`` attribute.
    Works with Samsung ovens, robot vacuums, and any device that supports
    the imageCapture capability.
    """

    def __init__(
        self,
        coordinator,
        api: SmartThingsApi,
        hass: HomeAssistant,
        *,
        entry_id: str,
        device: dict[str, Any],
        ref: EntityRef,
        name_suffix: str | None = None,
    ) -> None:
        Camera.__init__(self)
        SmartThingsDynamicBaseEntity.__init__(
            self, coordinator, entry_id=entry_id, device=device, ref=ref, name_suffix=name_suffix
        )
        self._api = api
        self.hass = hass
        self._last_take = 0.0

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        # Ask the device to take a new photo (throttled, see _TAKE_MIN_INTERVAL_S).
        now = time.monotonic()
        if now - self._last_take >= _TAKE_MIN_INTERVAL_S:
            self._last_take = now
            try:
                await self._api.async_execute_command(
                    self.ref.device_id,
                    self.ref.component_id,
                    IMAGE_CAPTURE_CAP,
                    "take",
                )
                # Give the device time to upload the image.
                await asyncio.sleep(_TAKE_DELAY_S)
                # Refresh coordinator to get the new image URL.
                await self.coordinator.async_request_refresh()
            except Exception:  # noqa: BLE001
                _LOGGER.debug("Failed to trigger imageCapture.take for %s", self.ref.device_id)

        url = self._attr_value()
        if not isinstance(url, str) or not url.startswith("http"):
            return self._cache_bytes
        return await self._async_cached_download(self.hass, self._api, url)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        cap = get_capability_status(
            self.coordinator.data or {},
            self.ref.device_id,
            self.ref.component_id,
            IMAGE_CAPTURE_CAP,
        )
        attrs: dict[str, Any] = {
            "image_url": self._attr_value(),
            "device_id": self.ref.device_id,
            "component": self.ref.component_id,
        }
        capture_time = (cap.get("captureTime") or {}).get("value")
        if capture_time:
            attrs["capture_time"] = capture_time
        return attrs


# ─── samsungce.viewInside camera (fridge) ──────────────────────────────────


class SmartThingsViewInsideCamera(_MediaCacheMixin, SmartThingsDynamicBaseEntity, Camera):
    """Camera using Samsung's ``samsungce.viewInside`` capability.

    Samsung Family Hub refrigerators take stills of the shelves after the door
    closes and publish them as file IDs in the ``contents`` attribute.  The most
    recent image is downloaded with the integration's OAuth token from the
    SmartThings UDO ``file_links`` endpoint.  A link expires about 10 minutes
    after it is published; an expired or refused link makes the camera send
    ``viewInside.refreshAll`` (at most once a minute) and keep showing the last
    downloaded photo meanwhile.
    """

    def __init__(
        self,
        coordinator,
        api: SmartThingsApi,
        hass: HomeAssistant,
        *,
        entry_id: str,
        device: dict[str, Any],
        ref: EntityRef,
        name_suffix: str | None = None,
        cid: str | None = None,
    ) -> None:
        Camera.__init__(self)
        SmartThingsDynamicBaseEntity.__init__(
            self, coordinator, entry_id=entry_id, device=device, ref=ref, name_suffix=name_suffix
        )
        self._api = api
        self.hass = hass
        self._cid = cid
        self._last_refresh = 0.0

    def _cap(self) -> dict[str, Any]:
        return get_capability_status(
            self.coordinator.data or {},
            self.ref.device_id,
            self.ref.component_id,
            VIEW_INSIDE_CAP,
        ) or {}

    def _latest_item(self) -> dict[str, Any] | None:
        """Return the most recent photo record ``{fileId, expiredTime, ...}``."""
        contents_payload = self._cap().get("contents")
        if not isinstance(contents_payload, dict):
            return None
        contents = contents_payload.get("value")
        if not isinstance(contents, list) or not contents:
            return None
        # The last item is usually the most recent photo.
        latest = contents[-1]
        if isinstance(latest, dict):
            return latest
        if isinstance(latest, str):
            return {"fileId": latest}
        return None

    def _get_latest_file_id(self) -> str | None:
        """Extract the most recent fileId from the contents attribute."""
        item = self._latest_item()
        if not item:
            return None
        return item.get("fileId") or item.get("id")

    def _link_expired(self, now: float | None = None) -> bool:
        item = self._latest_item() or {}
        exp = _parse_ts(item.get("expiredTime"))
        return exp is not None and exp <= (now if now is not None else time.time())

    async def _async_request_new_links(self) -> None:
        """Ask the fridge to publish fresh photo links (rate limited)."""
        now = time.monotonic()
        if now - self._last_refresh < _VIEW_INSIDE_REFRESH_MIN_INTERVAL_S:
            return
        self._last_refresh = now
        try:
            await self._api.async_execute_command(
                device_id=self.ref.device_id,
                component=self.ref.component_id,
                capability=VIEW_INSIDE_CAP,
                command="refreshAll",
                arguments=[],
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("viewInside.refreshAll failed for %s: %s", self.ref.device_id, err)
            return
        await self.coordinator.async_request_refresh()

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        file_id = self._get_latest_file_id()
        if not file_id:
            _LOGGER.debug("No viewInside fileId available for %s", self.ref.device_id)
            await self._async_request_new_links()
            return self._cache_bytes

        url = view_inside_image_url(file_id, self.ref.device_id, self._cid)
        if url == self._cache_url and self._cache_bytes:
            return self._cache_bytes
        if self._link_expired():
            await self._async_request_new_links()
            return self._cache_bytes

        data = await self._async_cached_download(self.hass, self._api, url)
        if self._cache_url != url:
            # Refused or failed: the link may have expired early.  Keep the last
            # photo (``data`` is the cached one or ``None``) and ask for new links.
            _LOGGER.debug("viewInside image download failed for %s", self.ref.device_id)
            await self._async_request_new_links()
        return data

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        cap = self._cap()
        item = self._latest_item() or {}
        contents_payload = cap.get("contents")
        num_images = 0
        if isinstance(contents_payload, dict):
            val = contents_payload.get("value")
            if isinstance(val, list):
                num_images = len(val)
        captured = cap.get("lastUpdatedTime")
        captured = captured.get("value") if isinstance(captured, dict) else None

        attrs: dict[str, Any] = {
            "device_id": self.ref.device_id,
            "component": self.ref.component_id,
            "capability": VIEW_INSIDE_CAP,
            "latest_file_id": item.get("fileId") or item.get("id"),
            "total_images": num_images,
            "captured_at": captured,
            "link_expires_at": item.get("expiredTime"),
            "focus_area": item.get("focusArea"),
        }
        return {k: v for k, v in attrs.items() if v is not None}


# ─── videoCapture camera (oven clips) ─────────────────────────────────────


class SmartThingsVideoCaptureCamera(_MediaCacheMixin, SmartThingsDynamicBaseEntity, Camera):
    """Camera showing the thumbnail of the latest ``videoCapture`` clip.

    Samsung ovens with a cooking camera store clips in the SmartThings cloud
    and describe the latest one in the ``clip`` attribute.  There is no public
    live stream, so the picture changes only when the device records a new
    clip (for example when the camera is opened in the SmartThings app).
    """

    def __init__(
        self,
        coordinator,
        api: SmartThingsApi,
        hass: HomeAssistant,
        *,
        entry_id: str,
        device: dict[str, Any],
        ref: EntityRef,
        name_suffix: str | None = None,
    ) -> None:
        Camera.__init__(self)
        SmartThingsDynamicBaseEntity.__init__(
            self, coordinator, entry_id=entry_id, device=device, ref=ref, name_suffix=name_suffix
        )
        self._api = api
        self.hass = hass

    def _clip(self) -> dict[str, Any]:
        val = self._attr_value()
        return val if isinstance(val, dict) else {}

    def thumbnail_url(self) -> str | None:
        return _first_url(self._clip(), _CLIP_THUMBNAIL_KEYS)

    def clip_url(self) -> str | None:
        return _first_url(self._clip(), _CLIP_VIDEO_KEYS)

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        url = self.thumbnail_url()
        if not url:
            return self._cache_bytes
        return await self._async_cached_download(self.hass, self._api, url)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        clip = self._clip()
        payload = self._attr_payload() or {}
        attrs: dict[str, Any] = {
            "device_id": self.ref.device_id,
            "component": self.ref.component_id,
            "capability": VIDEO_CAPTURE_CAP,
            "thumbnail_url": self.thumbnail_url(),
            "clip_url": self.clip_url(),
            "clip_status": clip.get("status"),
            "correlation_id": clip.get("correlationId"),
            "clip_time": payload.get("timestamp"),
            # Raw keys help diagnose devices that use other field names.
            "clip_keys": sorted(clip.keys()) or None,
        }
        return {k: v for k, v in attrs.items() if v is not None}


# ─── Generic / fallback camera ────────────────────────────────────────────


class SmartThingsGenericCamera(_MediaCacheMixin, SmartThingsDynamicBaseEntity, Camera):
    """Fallback camera for any capability that exposes an image URL.

    Does NOT send a ``take`` command — simply downloads whatever URL is
    currently in the ``image`` attribute.
    """

    def __init__(
        self,
        coordinator,
        hass: HomeAssistant,
        *,
        api: SmartThingsApi | None = None,
        entry_id: str,
        device: dict[str, Any],
        ref: EntityRef,
        name_suffix: str | None = None,
    ) -> None:
        Camera.__init__(self)
        SmartThingsDynamicBaseEntity.__init__(
            self, coordinator, entry_id=entry_id, device=device, ref=ref, name_suffix=name_suffix
        )
        self._api = api
        self.hass = hass

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        url = self._attr_value()
        if not isinstance(url, str) or not url.startswith("http"):
            return None
        return await self._async_cached_download(self.hass, self._api, url)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "image_url": self._attr_value(),
            "device_id": self.ref.device_id,
            "component": self.ref.component_id,
            "capability": self.ref.capability_id,
        }
