"""Tests for camera platform — discovery and image fetching logic."""

from __future__ import annotations

from typing import Any

import pytest

from custom_components.smartthings_dynamic.camera import (
    IMAGE_CAPTURE_CAP,
    VIEW_INSIDE_CAP,
    VIEW_INSIDE_IMAGE_URL,
    SmartThingsImageCaptureCamera,
    SmartThingsViewInsideCamera,
    SmartThingsGenericCamera,
)


# ─── Discovery helpers ─────────────────────────────────────────────────────


def _make_status(components: dict[str, dict[str, Any]]) -> dict:
    """Build a minimal coordinator-style status dict for one device."""
    return {
        "devices": {
            "dev-1": {
                "deviceId": "dev-1",
                "label": "Test Device",
                "components": [{"id": cid} for cid in components],
            }
        },
        "status": {
            "dev-1": {
                "components": components,
            }
        },
    }


# ─── viewInside: _get_latest_file_id ───────────────────────────────────────


class TestViewInsideFileId:
    """Unit-test the fileId extraction from samsungce.viewInside status."""

    def _make_camera(self, cap_status: dict[str, Any]) -> SmartThingsViewInsideCamera:
        """Build a ViewInsideCamera with fake coordinator data."""
        from unittest.mock import MagicMock

        data = _make_status({"main": {VIEW_INSIDE_CAP: cap_status}})

        coordinator = MagicMock()
        coordinator.data = data

        from custom_components.smartthings_dynamic.entity import EntityRef

        cam = object.__new__(SmartThingsViewInsideCamera)
        cam.coordinator = coordinator
        cam.ref = EntityRef(
            device_id="dev-1",
            component_id="main",
            capability_id=VIEW_INSIDE_CAP,
            attribute="contents",
        )
        return cam

    def test_extracts_file_id_from_dict_items(self):
        cap = {"contents": {"value": [{"fileId": "aaa"}, {"fileId": "bbb"}]}}
        cam = self._make_camera(cap)
        assert cam._get_latest_file_id() == "bbb"

    def test_extracts_id_field_as_fallback(self):
        cap = {"contents": {"value": [{"id": "only-id-field"}]}}
        cam = self._make_camera(cap)
        assert cam._get_latest_file_id() == "only-id-field"

    def test_handles_string_items(self):
        cap = {"contents": {"value": ["file-str-1", "file-str-2"]}}
        cam = self._make_camera(cap)
        assert cam._get_latest_file_id() == "file-str-2"

    def test_empty_contents_list(self):
        cap = {"contents": {"value": []}}
        cam = self._make_camera(cap)
        assert cam._get_latest_file_id() is None

    def test_contents_not_a_list(self):
        cap = {"contents": {"value": "unexpected"}}
        cam = self._make_camera(cap)
        assert cam._get_latest_file_id() is None

    def test_no_contents_attribute(self):
        cap = {"otherAttr": {"value": 123}}
        cam = self._make_camera(cap)
        assert cam._get_latest_file_id() is None

    def test_contents_payload_not_dict(self):
        cap = {"contents": "bad"}
        cam = self._make_camera(cap)
        assert cam._get_latest_file_id() is None

    def test_single_item_list(self):
        cap = {"contents": {"value": [{"fileId": "only-one"}]}}
        cam = self._make_camera(cap)
        assert cam._get_latest_file_id() == "only-one"

    def test_item_without_file_id_or_id(self):
        cap = {"contents": {"value": [{"something": "else"}]}}
        cam = self._make_camera(cap)
        assert cam._get_latest_file_id() is None

    def test_numeric_item_returns_none(self):
        cap = {"contents": {"value": [12345]}}
        cam = self._make_camera(cap)
        assert cam._get_latest_file_id() is None


# ─── viewInside: image URL construction ────────────────────────────────────


class TestViewInsideImageUrl:
    def test_url_template(self):
        url = VIEW_INSIDE_IMAGE_URL.format(file_id="abc-123")
        assert url == "https://client.smartthings.com/udo/file_links/abc-123"

    def test_url_with_special_chars(self):
        url = VIEW_INSIDE_IMAGE_URL.format(file_id="file/with+chars")
        assert "file/with+chars" in url


# ─── imageCapture: extra_state_attributes ──────────────────────────────────


class TestImageCaptureAttributes:
    def _make_camera(self, cap_status: dict[str, Any]) -> SmartThingsImageCaptureCamera:
        from unittest.mock import MagicMock

        data = _make_status({"main": {IMAGE_CAPTURE_CAP: cap_status}})

        coordinator = MagicMock()
        coordinator.data = data

        from custom_components.smartthings_dynamic.entity import EntityRef

        cam = object.__new__(SmartThingsImageCaptureCamera)
        cam.coordinator = coordinator
        cam.ref = EntityRef(
            device_id="dev-1",
            component_id="main",
            capability_id=IMAGE_CAPTURE_CAP,
            attribute="image",
        )
        cam._device_label = "Oven"
        cam._component_label = "main"
        cam._name_suffix = "imageCapture"
        cam._entry_id = "entry-1"
        cam._device = {"deviceId": "dev-1"}
        return cam

    def test_includes_capture_time(self):
        cap = {
            "image": {"value": "https://img.example.com/photo.jpg"},
            "captureTime": {"value": "2025-06-15T10:30:00Z"},
        }
        cam = self._make_camera(cap)
        attrs = cam.extra_state_attributes
        assert attrs["capture_time"] == "2025-06-15T10:30:00Z"
        assert attrs["image_url"] == "https://img.example.com/photo.jpg"

    def test_no_capture_time(self):
        cap = {"image": {"value": "https://img.example.com/photo.jpg"}}
        cam = self._make_camera(cap)
        attrs = cam.extra_state_attributes
        assert "capture_time" not in attrs

    def test_image_url_none(self):
        cap = {"image": {"value": None}}
        cam = self._make_camera(cap)
        attrs = cam.extra_state_attributes
        assert attrs["image_url"] is None


# ─── viewInside: extra_state_attributes ────────────────────────────────────


class TestViewInsideAttributes:
    def _make_camera(self, cap_status: dict[str, Any]) -> SmartThingsViewInsideCamera:
        from unittest.mock import MagicMock

        data = _make_status({"main": {VIEW_INSIDE_CAP: cap_status}})

        coordinator = MagicMock()
        coordinator.data = data

        from custom_components.smartthings_dynamic.entity import EntityRef

        cam = object.__new__(SmartThingsViewInsideCamera)
        cam.coordinator = coordinator
        cam.ref = EntityRef(
            device_id="dev-1",
            component_id="main",
            capability_id=VIEW_INSIDE_CAP,
            attribute="contents",
        )
        cam._device_label = "Fridge"
        cam._component_label = "main"
        cam._name_suffix = "viewInside"
        cam._entry_id = "entry-1"
        cam._device = {"deviceId": "dev-1"}
        return cam

    def test_shows_total_images_and_file_id(self):
        cap = {"contents": {"value": [{"fileId": "a"}, {"fileId": "b"}, {"fileId": "c"}]}}
        cam = self._make_camera(cap)
        attrs = cam.extra_state_attributes
        assert attrs["total_images"] == 3
        assert attrs["latest_file_id"] == "c"

    def test_empty_contents(self):
        cap = {"contents": {"value": []}}
        cam = self._make_camera(cap)
        attrs = cam.extra_state_attributes
        assert attrs["total_images"] == 0
        assert "latest_file_id" not in attrs  # None filtered out

    def test_no_contents(self):
        cap = {}
        cam = self._make_camera(cap)
        attrs = cam.extra_state_attributes
        assert attrs["total_images"] == 0


# ─── Constants ──────────────────────────────────────────────────────────────


class TestCameraConstants:
    def test_view_inside_cap(self):
        assert VIEW_INSIDE_CAP == "samsungce.viewInside"

    def test_image_capture_cap(self):
        assert IMAGE_CAPTURE_CAP == "imageCapture"


# ─── videoCapture: clip thumbnail camera ───────────────────────────────────

from unittest.mock import AsyncMock, MagicMock  # noqa: E402

from custom_components.smartthings_dynamic import camera as camera_mod  # noqa: E402
from custom_components.smartthings_dynamic.camera import (  # noqa: E402
    VIDEO_CAPTURE_CAP,
    SmartThingsVideoCaptureCamera,
    async_download_media,
)


def _video_camera(clip_value: Any, api: Any = None) -> SmartThingsVideoCaptureCamera:
    from custom_components.smartthings_dynamic.entity import EntityRef

    clip = {"clip": {"value": clip_value, "timestamp": "2026-11-07T12:39:11Z"}}
    data = _make_status({"main": {VIDEO_CAPTURE_CAP: clip}})
    coordinator = MagicMock()
    coordinator.data = data
    cam = object.__new__(SmartThingsVideoCaptureCamera)
    cam.coordinator = coordinator
    cam.ref = EntityRef(device_id="dev-1", component_id="main", capability_id=VIDEO_CAPTURE_CAP, attribute="clip")
    cam._api = api
    cam.hass = MagicMock()
    return cam


CLIP = {
    "clipPath": "https://mediaserv.example.st-av.net/clip?id=1",
    "thumbnailPath": "https://mediaserv.example.st-av.net/image?id=1",
    "status": "COMPLETE",
    "correlationId": "abc",
}


class TestVideoCaptureCamera:
    def test_urls_from_clip(self):
        cam = _video_camera(CLIP)
        assert cam.thumbnail_url() == CLIP["thumbnailPath"]
        assert cam.clip_url() == CLIP["clipPath"]

    def test_attributes(self):
        attrs = _video_camera(CLIP).extra_state_attributes
        assert attrs["thumbnail_url"] == CLIP["thumbnailPath"]
        assert attrs["clip_status"] == "COMPLETE"
        assert attrs["correlation_id"] == "abc"
        assert attrs["clip_time"] == "2026-11-07T12:39:11Z"
        assert attrs["clip_keys"] == sorted(CLIP)

    def test_no_urls(self):
        cam = _video_camera({"status": "COMPLETE"})
        assert cam.thumbnail_url() is None
        assert "thumbnail_url" not in cam.extra_state_attributes

    async def test_image_downloads_thumbnail_with_token(self):
        api = MagicMock()
        api.async_fetch_media = AsyncMock(return_value=b"jpeg")
        cam = _video_camera(CLIP, api)
        assert await cam.async_camera_image() == b"jpeg"
        api.async_fetch_media.assert_awaited_once_with(CLIP["thumbnailPath"])
        # Same URL is served from cache.
        assert await cam.async_camera_image() == b"jpeg"
        assert api.async_fetch_media.await_count == 1

    async def test_image_none_without_thumbnail(self):
        cam = _video_camera({"status": "COMPLETE"}, MagicMock())
        assert await cam.async_camera_image() is None


class TestDownloadMedia:
    async def test_falls_back_to_plain_request(self, monkeypatch):
        api = MagicMock()
        api.async_fetch_media = AsyncMock(side_effect=RuntimeError("403"))
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.read = AsyncMock(return_value=b"plain")
        session = MagicMock()
        session.get = AsyncMock(return_value=resp)
        monkeypatch.setattr(camera_mod, "async_get_clientsession", lambda hass: session)
        assert await async_download_media(MagicMock(), api, "https://x/y") == b"plain"

    async def test_returns_none_when_all_fail(self, monkeypatch):
        from aiohttp import ClientError

        api = MagicMock()
        api.async_fetch_media = AsyncMock(side_effect=RuntimeError("403"))
        session = MagicMock()
        session.get = AsyncMock(side_effect=ClientError("boom"))
        monkeypatch.setattr(camera_mod, "async_get_clientsession", lambda hass: session)
        assert await async_download_media(MagicMock(), api, "https://x/y") is None


class TestImageCaptureThrottle:
    async def test_take_sent_once_per_interval(self, monkeypatch):
        from custom_components.smartthings_dynamic.entity import EntityRef

        data = _make_status({"main": {IMAGE_CAPTURE_CAP: {"image": {"value": "https://img/1"}}}})
        coordinator = MagicMock()
        coordinator.data = data
        coordinator.async_request_refresh = AsyncMock()
        api = MagicMock()
        api.async_execute_command = AsyncMock()
        api.async_fetch_media = AsyncMock(return_value=b"img")
        monkeypatch.setattr(camera_mod, "_TAKE_DELAY_S", 0)

        cam = object.__new__(SmartThingsImageCaptureCamera)
        cam.coordinator = coordinator
        cam.ref = EntityRef(device_id="dev-1", component_id="main", capability_id=IMAGE_CAPTURE_CAP, attribute="image")
        cam._api = api
        cam.hass = MagicMock()
        cam._last_take = 0.0

        assert await cam.async_camera_image() == b"img"
        assert await cam.async_camera_image() == b"img"
        assert api.async_execute_command.await_count == 1
        api.async_fetch_media.assert_awaited_once_with("https://img/1")
