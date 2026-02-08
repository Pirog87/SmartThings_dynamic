# SmartThings Dynamic Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![HA Version](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue.svg)](https://www.home-assistant.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A custom Home Assistant integration that provides **full, dynamic control** of Samsung SmartThings appliances — going far beyond the official integration's capabilities.

## Why this integration?

The official Home Assistant SmartThings integration exposes only a limited subset of device capabilities. If you own Samsung appliances (washing machines, dryers, robot vacuums, ovens, refrigerators, etc.), you've likely noticed that many features are simply missing.

**SmartThings Dynamic** solves this by automatically discovering **all** capabilities, attributes, and commands reported by the SmartThings API, and dynamically creating the appropriate Home Assistant entities for each one.

After Samsung's December 2024 API changes that introduced stricter PAT token limits and pushed toward OAuth2 authentication, this integration uses **OAuth2 with Basic Auth** for reliable, long-term connectivity.

## Features

- **Dynamic entity creation** — automatically maps SmartThings capabilities to HA entity types:
  - `sensor` — numeric and text attributes
  - `binary_sensor` — boolean attributes (on/off, open/closed)
  - `switch` — capabilities with on/off commands
  - `select` — commands with enum arguments
  - `number` — commands with numeric arguments
  - `button` — commands with no arguments
  - `vacuum` — specialized support for Samsung robot vacuums (JetBot)
  - `camera` — device image feeds
- **Multi-component devices** — full support for devices with multiple components (e.g., refrigerator with fridge + freezer + flex zone)
- **Three discovery modes:**
  - Standard — core entities
  - `expose_command_buttons` — exposes all commands as button entities
  - `aggressive_mode` — creates additional controls from `supported*` attribute lists
- **Webhook support** — optional real-time updates via SmartThings SmartApp webhooks, with automatic fallback to polling
- **Custom service** `smartthings_dynamic.send_command` — send any command to any device, even if no entity exists for it
- **Capability caching** — reduces API calls by caching SmartThings capability definitions
- **Configurable polling** — default 30s, adjustable per your needs

## Supported devices

Tested with Samsung appliances including:

| Device type | Capabilities |
|---|---|
| 🤖 Robot vacuum (JetBot) | Operating state, cleaning modes, maps, battery, dock status |
| 👕 Washing machine | Programs, temperature, spin speed, remaining time, status |
| 🌀 Dryer | Programs, drying level, time, status |
| ❄️ Refrigerator | Temperatures (fridge/freezer/flex), modes, door status, rapid cooling/freezing |
| 🔥 Oven | Oven modes, temperatures, timer, operating state |
| 📡 Microwave | Power level, time, operating state |
| 🍽️ Dishwasher | Programs, status, remaining time |
| ♨️ Induction hob | Burner status, power levels |

> The integration works with **any** SmartThings device — the above are simply the ones that have been extensively tested.

## Installation

### HACS (recommended)

1. Open HACS in Home Assistant
2. Go to **Integrations** → **⋮** (top right) → **Custom repositories**
3. Add this repository URL and select category **Integration**
4. Search for "SmartThings Dynamic" and install
5. Restart Home Assistant

### Manual

1. Copy the `custom_components/smartthings_dynamic` folder to your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

### Prerequisites

- A Samsung SmartThings developer account ([developer.smartthings.com](https://developer.smartthings.com))
- **SmartThings CLI** installed on your computer
- **Node.js** (required for SmartThings CLI)
- Home Assistant with external HTTPS access (e.g., Nabu Casa subscription)

### Step 1: Install SmartThings CLI

**Windows (via npm):**
```bash
npm install -g @smartthings/cli
```

**Windows (installer):**
Download the MSI installer from [SmartThings CLI Releases](https://github.com/SmartThingsCommunity/smartthings-cli/releases).

**macOS:**
```bash
brew install smartthings
# or
npm install -g @smartthings/cli
```

**Linux:**
```bash
npm install -g @smartthings/cli
```

Verify the installation:
```bash
smartthings --version
```

### Step 2: Create an OAuth-In App

Run the app creation wizard:
```bash
smartthings apps:create
```

When prompted:

1. **App type:** Select **OAuth-In App**
2. **Display Name:** `Home Assistant SmartThings Dynamic`
3. **Description:** `Full SmartThings device control for Home Assistant`
4. **Target URL:** Your Home Assistant external URL, e.g.:
   ```
   https://your-nabu-casa-id.ui.nabu.casa
   ```
   > ⚠️ Must be **HTTPS** — Samsung rejects HTTP URLs
5. **Permissions/Scopes** — select at minimum:
   - `r:devices:*` (read devices)
   - `x:devices:*` (execute device commands)
   - `r:locations:*` (read locations)
   - `r:scenes:*` (read scenes)
   - `x:scenes:*` (execute scenes)
6. **Redirect URI:** Your HA OAuth callback URL

After creation, the CLI will display:

```
App ID:        xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
Client ID:     xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
Client Secret: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

> ⚠️ **Save these values immediately!** The Client Secret is shown only once.

### Step 3: (Optional) List your devices

You can preview your SmartThings devices before setting up the integration:

```bash
smartthings devices
```

> **Note:** You no longer need to manually configure device IDs. The integration automatically discovers all devices during setup and lets you choose which ones to monitor.

The naming convention is `st_<device_name>_device_id`. You can use any name you like (including custom nicknames for your appliances) — these keys are then referenced in your HA packages and automations:

```yaml
# Example usage in a package file
template:
  - sensor:
      - name: "Washing Machine - Status"
        state: >
          {{ states('sensor.smartthings_dynamic_washer_machineState') }}
```

> ⚠️ **Never commit `secrets.yaml` to your repository!** It's already excluded by `.gitignore`.

### Step 4: Add the integration to Home Assistant

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for **SmartThings Dynamic**
3. Enter your **Client ID** and **Client Secret** from Step 2
4. Complete the OAuth2 authorization flow
5. **Select the devices** you want to monitor from the automatically discovered list (all devices are selected by default)

You can change the monitored devices at any time in the integration's **Options** (Settings → Devices & Services → SmartThings Dynamic → Configure).

## Usage

### Entities

After setup, entities appear automatically based on each device's capabilities. Entity IDs follow the pattern:

```
{domain}.smartthings_dynamic_{device_name}_{capability}_{attribute}
```

### Sending custom commands

Use the `smartthings_dynamic.send_command` service to send any SmartThings command:

```yaml
service: smartthings_dynamic.send_command
data:
  device_id: "your-device-id-here"
  component: "main"
  capability: "samsungce.washerOperatingState"
  command: "start"
  args: []
```

### Template sensors (packages)

For advanced dashboards, you can create template sensors in HA packages that filter and transform the dynamic entities. Example for a robot vacuum:

```yaml
template:
  - sensor:
      - name: "Vacuum - Battery"
        state: >
          {{ states('sensor.smartthings_dynamic_vacuum_battery') | int(0) }}
        unit_of_measurement: "%"
        device_class: battery
```

## Configuration options

| Option | Default | Description |
|---|---|---|
| `scan_interval` | 30 | Polling interval in seconds |
| `expose_command_buttons` | false | Create button entities for all commands |
| `expose_raw_sensors` | false | Expose complex attributes as raw sensors |
| `aggressive_mode` | false | Create extra controls from supported* lists |

## Webhook (real-time updates)

The integration **automatically detects** whether your Home Assistant instance has an external URL configured. If it does, a webhook is registered and SmartThings pushes device events in real-time — no manual configuration needed.

- **External URL available** — webhook is active, polling reduced to a 5-minute backup interval for consistency checks. Device state changes appear instantly.
- **No external URL** — the integration uses standard polling (default 30s). No webhook is registered.

### Requirements (for real-time mode)

- Home Assistant must be accessible via an **external HTTPS URL** (e.g., Nabu Casa, reverse proxy with SSL).
- The external URL must be configured in **Settings → System → Network → Home Assistant URL**.

Once the external URL is set, restart the integration and webhooks will activate automatically.

## Troubleshooting

### Entities show "unavailable"

- Verify your OAuth2 credentials are valid
- Check that the device is online in the SmartThings app
- Review HA logs: **Settings** → **System** → **Logs**, filter by `smartthings_dynamic`

### Rate limiting

Samsung enforces rate limits (350 requests / 5 minutes per SmartApp). If you have many devices, consider increasing `scan_interval`.

### After Samsung API changes (Dec 2024)

This integration uses OAuth2 authentication, which is not affected by the PAT token limitations introduced in December 2024. If you're migrating from a PAT-based integration, you'll need to set up OAuth2 credentials through the SmartThings developer portal.

## Development

```bash
# Clone the repository
git clone https://github.com/Pirog87/SmartThings_dynamic.git

# The integration structure
custom_components/smartthings_dynamic/
├── __init__.py              # Integration setup & OAuth2 flow
├── api.py                   # SmartThings API client
├── coordinator.py           # Data update coordinator
├── config_flow.py           # Configuration UI flow
├── const.py                 # Constants
├── entity.py                # Base entity class
├── helpers.py               # Utility functions
├── sensor.py                # Sensor platform
├── binary_sensor.py         # Binary sensor platform
├── switch.py                # Switch platform
├── select.py                # Select platform
├── number.py                # Number platform
├── button.py                # Button platform
├── vacuum.py                # Vacuum platform (Samsung JetBot)
├── camera.py                # Camera platform
├── webhook.py               # Webhook handler for real-time events
├── application_credentials.py
├── manifest.json
├── services.yaml
├── strings.json
└── translations/
    ├── en.json              # English translation
    └── pl.json              # Polish translation
```

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/new-device-support`)
3. Commit your changes (`git commit -m 'Add support for Samsung TV capabilities'`)
4. Push to the branch (`git push origin feature/new-device-support`)
5. Open a Pull Request

## Roadmap

- [x] Webhook support for real-time updates (instead of polling)
- [x] HACS default repository listing (manifest, hacs.json, translations)
- [x] Automatic device discovery (without manual device ID entry)
- [ ] Lovelace dashboard cards for appliance controls
- [x] Energy monitoring integration (state_class, device_class, unit normalisation for HA Energy Dashboard)

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [Samsung SmartThings API Documentation](https://developer.smartthings.com/docs/getting-started/architecture-of-smartthings)
- [Home Assistant Developer Documentation](https://developers.home-assistant.io/)
- Home Assistant community for feedback and testing

---

*This integration is not affiliated with or endorsed by Samsung Electronics.*
