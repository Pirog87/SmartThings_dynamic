"""Constants for the SmartThings Dynamic integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "smartthings_dynamic"

SMARTTHINGS_API_BASE: Final = "https://api.smartthings.com/v1"
OAUTH2_AUTHORIZE_URL: Final = "https://api.smartthings.com/oauth/authorize"
OAUTH2_TOKEN_URL: Final = "https://api.smartthings.com/oauth/token"

# Minimal scopes needed to read device state + execute commands.
OAUTH2_SCOPES: Final[list[str]] = ["r:devices:*", "x:devices:*"]

# --- POLLING CONFIGURATION ---
# Default interval when devices are IDLE (saves API limits)
DEFAULT_SCAN_INTERVAL: Final = timedelta(seconds=30)
# Aggressive interval when devices are ACTIVE (running, heating, spinning)
ACTIVE_SCAN_INTERVAL: Final = timedelta(seconds=10)

DEFAULT_MAX_CONCURRENT_REQUESTS: Final = 10

# Options keys
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_MAX_CONCURRENT_REQUESTS: Final = "max_concurrent_requests"
CONF_EXPOSE_COMMAND_BUTTONS: Final = "expose_command_buttons"
CONF_EXPOSE_RAW_SENSORS: Final = "expose_raw_sensors"
CONF_INCLUDE_CONTROL_ATTRIBUTES_AS_SENSORS: Final = "include_control_attributes_as_sensors"
CONF_AGGRESSIVE_MODE: Final = "aggressive_mode"

# Aggressive mode enables additional heuristics for creating control entities
DEFAULT_AGGRESSIVE_MODE: Final = True

# Platforms
PLATFORMS: Final[list[str]] = [
    "sensor",
    "binary_sensor",
    "switch",
    "button",
    "select",
    "number",
    "camera",
    "vacuum",
]