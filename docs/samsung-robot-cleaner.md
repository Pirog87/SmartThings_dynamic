# Samsung robot cleaners: what the SmartThings API can and cannot do

Research notes for the Samsung Bespoke Jet Bot Combo (`JETBOT_COMBOT_9X00_24K`,
presentation id `DA-RVC-MAP-01011`). Checked against the live device capability list, the
capability command tables shipped with `pysmartthings`, Home Assistant core and the
SmartThings community threads listed at the bottom.

**Last verified: 2026-08-25.**

## TL;DR

Cleaning type, driving mode, water spray level and suction power are all controllable through
the public SmartThings REST API. **Selecting which room to clean is not.** The map
capabilities are read-only, and no other capability on the device accepts an area id.

## What the device exposes

### Controllable (capability → command → values)

| Mobile app option | Capability | Command | Values |
| --- | --- | --- | --- |
| Cleaning method | `samsungce.robotCleanerCleaningType` | `setCleaningType` | `vacuum`, `mop`, `vacuumAndMopTogether`, `mopAfterVacuum` |
| Water amount | `samsungce.robotCleanerWaterSprayLevel` | `setWaterSprayLevel` | `high`, `mediumHigh`, `medium`, `mediumLow`, `low` |
| Driving style | `samsungce.robotCleanerDrivingMode` | `setDrivingMode` | `areaThenWalls`, `wallFirst`, `quickCleaningZigzagPattern` |
| Suction power | `robotCleanerTurboMode` | `setRobotCleanerTurboMode` | `on`, `off`, `silence`, `extraSilence` |
| Start / pause / resume / dock / cancel | `samsungce.robotCleanerOperatingState` | `start`, `pause`, `resume`, `returnToHome`, `cancelRemainingJob`, `setOperatingState` | — |
| Cleaning mode | `samsungce.robotCleanerCleaningMode` | `setCleaningMode` | `stop`, `auto`, `manual`, `spot`, `area`, `object`, `map`, `pet`, `uncleanedObject`, `patternMap`, `creatingMap` |
| Repeat cleaning | `samsungce.robotCleanerCleaningMode` | `enableRepeatMode`, `disableRepeatMode` | — |

`setCleaningMode` takes a single enum argument. `map` and `area` select *how* the robot
cleans, not *where*: there is no second argument for a map or area id.

### Read-only (no commands at all)

| Capability | Attributes |
| --- | --- |
| `samsungce.robotCleanerMapAreaInfo` | `areaInfo` — the room list, e.g. `[{"id": "5", "name": "Kitchen"}]` |
| `samsungce.robotCleanerMapList` | `maps` — maps with their rooms and objects |
| `samsungce.robotCleanerMapMetadata` | `cellSize` |
| `samsungce.robotCleanerMapCleaningInfo` | `area`, `cleanedExtent`, `nearObject`, `remainingTime` |

The room ids needed for room-targeted cleaning are therefore readable, but nothing on the
device accepts them.

## Why room selection does not work

1. All four map capabilities have an empty command list. This holds both in the capability
   command table of `pysmartthings` and in the capability definitions this integration
   fetches at runtime from `GET /v1/capabilities/{id}/{version}` — no command entities are
   generated for them.
2. The standard `serviceArea` capability (`selectAreas` / `supportedAreas`, the SmartThings
   counterpart of the Matter 1.4 Service Area cluster) is the sanctioned way to do room
   selection, and Home Assistant already consumes it. Samsung's own robot cleaners do not
   implement it — it is absent from the device's capability list.
3. SmartThings staff have confirmed on the community forum that the mobile app talks to the
   robot directly and that not every app feature has an API equivalent. When a room clean is
   started from the app, the API only reports a changed `cleaningMode`.
4. `samsungce.robotCleanerFeatureVisibility.visibleFeatures` contains `SelectRoom`, which is
   a hint to the mobile app's UI, not an API surface.

## Capabilities that do carry area ids

Three schedule-style capabilities expose `mapId` and `areaIds` attributes:

- `samsungce.robotCleanerPatrol` (`setPatrol`)
- `samsungce.robotCleanerPetCleaningSchedule` (`setSchedule`)
- `samsungce.robotCleanerPetMonitor` (`setMonitor`)

On `DA-RVC-MAP-01011` all three report `obsoleted: true`, so they are unlikely to do
anything. `samsungce.robotCleanerReservation` (`addReservation`, `editReservation`,
`deleteReservation`, `deleteReservations`) is *not* obsoleted, and its `reservations`
attribute is a list of objects whose schema is not published. If a reservation object turns
out to carry `mapId` + `areaIds`, scheduling a one-off reservation would be an indirect way
to clean selected rooms.

To check without actuating the robot:

1. Create a schedule with specific rooms in the SmartThings app.
2. Read the resulting object:
   ```yaml
   action: smartthings_dynamic.dump_device
   data:
     device_id: <your device id>
   response_variable: dump
   ```
   and look at `status.components.main["samsungce.robotCleanerReservation"].reservations`.
3. Fetch the argument schema of the command:
   ```yaml
   action: smartthings_dynamic.dump_capability
   data:
     capability: samsungce.robotCleanerReservation
   response_variable: definition
   ```

Both services only issue GET requests.

The `execute` capability (an OCF pass-through, present on this device) is the other untested
route. Its resource paths for robot cleaners are undocumented.

## Home Assistant side

Home Assistant core has everything needed for room cleaning already: the `vacuum.clean_area`
action, `VacuumEntityFeature.CLEAN_AREA`, `async_get_segments()` and the *Map vacuum
segments to areas* dialog. The official `smartthings` integration's vacuum platform only
implements start, pause, return home and fan speed — matching what the API allows.

## Sources

- [Home Assistant SmartThings integration](https://www.home-assistant.io/integrations/smartthings/)
- [Home Assistant vacuum integration — cleaning specific areas](https://www.home-assistant.io/integrations/vacuum/)
- [Clean specific room using API? — SmartThings Community](https://community.smartthings.com/t/clean-specific-room-using-api/286594)
- [JetBot Area Clean from the API — SmartThings Community](https://community.smartthings.com/t/jetbot-area-clean-from-the-api/272025)
