"""Application Credentials for SmartThings Dynamic.

This enables users to enter their own SmartThings OAuth client_id/client_secret in the UI.

SmartThings docs state that OAuth apps (clientId/clientSecret) are created via SmartThings CLI.
"""

from __future__ import annotations

import base64
import logging
from json import JSONDecodeError
from typing import Any, cast

from aiohttp import ClientError

from homeassistant.components.application_credentials import (
    AuthImplementation,
    AuthorizationServer,
    ClientCredential,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client

from .const import DOMAIN, OAUTH2_AUTHORIZE_URL, OAUTH2_TOKEN_URL

_LOGGER = logging.getLogger(__name__)


class SmartThingsAuthImplementation(AuthImplementation):
    """Custom OAuth2 implementation for SmartThings.

    SmartThings documentation recommends using HTTP Basic Auth with clientId/clientSecret
    when calling the token endpoint. We implement that explicitly to avoid compatibility issues.
    """

    @property
    def name(self) -> str:
        # Shown in the "pick implementation" step (if multiple credentials exist)
        return "Application Credentials"

    async def _token_request(self, data: dict[str, Any]) -> dict:
        """Make a token request (authorization_code or refresh_token)."""
        session = aiohttp_client.async_get_clientsession(self.hass)

        # SmartThings expects client_id in the form body.
        data["client_id"] = self.client_id

        # SmartThings docs recommend Basic auth header.
        basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        headers = {"Authorization": f"Basic {basic}"}

        _LOGGER.debug("Sending token request to %s", self.token_url)

        resp = await session.post(self.token_url, data=data, headers=headers)

        if resp.status >= 400:
            try:
                error_response = await resp.json()
            except (ClientError, JSONDecodeError):
                error_response = {}

            error_code = error_response.get("error", "unknown")
            error_description = error_response.get("error_description", "unknown error")
            _LOGGER.error(
                "Token request for %s failed (%s): %s",
                self.domain,
                error_code,
                error_description,
            )
            resp.raise_for_status()

        return cast(dict, await resp.json())


async def async_get_auth_implementation(
    hass: HomeAssistant, auth_domain: str, credential: ClientCredential
):
    """Return auth implementation."""
    return SmartThingsAuthImplementation(
        hass,
        auth_domain,
        credential,
        AuthorizationServer(
            authorize_url=OAUTH2_AUTHORIZE_URL,
            token_url=OAUTH2_TOKEN_URL,
        ),
    )


async def async_get_description_placeholders(hass: HomeAssistant) -> dict[str, str]:
    """Return description placeholders for the credentials UI."""
    return {
        "docs_url": "https://developer.smartthings.com/docs/getting-started/quickstart",
        "cli_url": "https://developer.smartthings.com/docs/sdks/cli",
    }
