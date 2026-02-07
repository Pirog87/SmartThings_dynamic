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
- OAuth2 credentials (Client ID and Client Secret) from a registered SmartApp
- Your SmartThings device IDs

### Setup

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for **SmartThings Dynamic**
3. Enter your OAuth2 credentials when prompted
4. Select the devices you want to integrate

### Device IDs

You can find your device IDs through the SmartThings API or CLI:

```bash
# Using SmartThings CLI
smartthings devices
```

Or via the API:
```
GET https://api.smartthings.com/v1/devices
```

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
git clone https://github.com/Pirog87/ha-smartthings-dynamic.git

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
├── application_credentials.py
├── manifest.json
├── services.yaml
├── strings.json
└── translations/
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

- [ ] Webhook support for real-time updates (instead of polling)
- [ ] HACS default repository listing
- [ ] Automatic device discovery (without manual device ID entry)
- [ ] Lovelace dashboard cards for appliance controls
- [ ] Energy monitoring integration

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [Samsung SmartThings API Documentation](https://developer.smartthings.com/docs/getting-started/architecture-of-smartthings)
- [Home Assistant Developer Documentation](https://developers.home-assistant.io/)
- Home Assistant community for feedback and testing

---

*This integration is not affiliated with or endorsed by Samsung Electronics.*
