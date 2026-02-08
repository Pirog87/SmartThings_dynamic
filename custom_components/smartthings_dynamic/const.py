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
CONF_DEVICE_IDS: Final = "device_ids"

# Aggressive mode enables additional heuristics for creating control entities
DEFAULT_AGGRESSIVE_MODE: Final = True

# --- WEBHOOK / REAL-TIME UPDATES ---
# When webhooks are active, polling backs off to this interval (consistency check).
WEBHOOK_BACKUP_POLL_INTERVAL: Final = timedelta(minutes=5)

# --- ENERGY MONITORING ---
# Sub-keys extracted from powerConsumption / custom energy capability dicts.
ENERGY_SUB_ATTRIBUTES: Final[list[str]] = [
    "energy",        # cumulative energy (Wh)
    "deltaEnergy",   # energy since last report (Wh)
    "power",         # instantaneous power (W)
    "powerEnergy",   # energy at current power level (Wh)
    "start",         # measurement period start
    "end",           # measurement period end
]

# Unit normalisation map – SmartThings sometimes sends long-form or variant units.
ENERGY_UNIT_MAP: Final[dict[str, str]] = {
    "W": "W",
    "Watts": "W",
    "watt": "W",
    "kW": "kW",
    "Kilowatts": "kW",
    "Wh": "Wh",
    "watt-hours": "Wh",
    "kWh": "kWh",
    "kilowatt-hours": "kWh",
    "V": "V",
    "Volts": "V",
    "A": "A",
    "Amps": "A",
    "mA": "mA",
    "%": "%",
}

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
