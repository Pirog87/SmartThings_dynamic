"""SmartThings API client used by the SmartThings Dynamic integration."""

from __future__ import annotations

import logging
from typing import Any

from aiohttp import ClientResponseError

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import config_entry_oauth2_flow

from .const import SMARTTHINGS_API_BASE

_LOGGER = logging.getLogger(__name__)


DEFAULT_HEADERS = {
    "Accept": "application/vnd.smartthings+json;v=1",
    "Content-Type": "application/json",
}


class SmartThingsApi:
    """Small async client for the SmartThings REST API."""

    def __init__(self, oauth_session: config_entry_oauth2_flow.OAuth2Session) -> None:
        self._oauth = oauth_session
        self._capability_cache: dict[tuple[str, int], dict[str, Any]] = {}

    async def _request_json(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json_data: Any | None = None,
    ) -> Any:
        req_headers = {**DEFAULT_HEADERS, **(headers or {})}
        try:
            resp = await self._oauth.async_request(
                method,
                url,
                headers=req_headers,
                json=json_data,
            )
            resp.raise_for_status()
            return await resp.json()
        except ClientResponseError as err:
            # If refresh token is invalid or access is revoked, SmartThings returns 401/403.
            if err.status in (401, 403):
                raise ConfigEntryAuthFailed("SmartThings authentication failed") from err
            raise

    async def async_list_devices(self) -> dict[str, Any]:
        return await self._request_json("get", f"{SMARTTHINGS_API_BASE}/devices")

    async def async_get_device(self, device_id: str) -> dict[str, Any]:
        return await self._request_json("get", f"{SMARTTHINGS_API_BASE}/devices/{device_id}")

    async def async_get_device_status(self, device_id: str) -> dict[str, Any]:
        return await self._request_json("get", f"{SMARTTHINGS_API_BASE}/devices/{device_id}/status")

    async def async_execute_command(
        self,
        device_id: str,
        component: str,
        capability: str,
        command: str,
        arguments: list[Any] | None = None,
    ) -> None:
        payload = {
            "commands": [
                {
                    "component": component,
                    "capability": capability,
                    "command": command,
                    "arguments": arguments or [],
                }
            ]
        }
        _LOGGER.debug("Sending command payload: %s to device %s", payload, device_id)
        await self._request_json(
            "post",
            f"{SMARTTHINGS_API_BASE}/devices/{device_id}/commands",
            json_data=payload,
        )

    async def async_get_capability_definition(self, capability_id: str, version: int) -> dict[str, Any]:
        key = (capability_id, int(version))
        if key in self._capability_cache:
            return self._capability_cache[key]

        data = await self._request_json(
            "get",
            f"{SMARTTHINGS_API_BASE}/capabilities/{capability_id}/{int(version)}",
        )
        self._capability_cache[key] = data
        return data
