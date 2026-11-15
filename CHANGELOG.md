## 1.3.17

- Create cover entities even when the device reports no channel list, and
  apply the same guard to every platform. This restores the open/close cover
  controls for devices such as the MRS100.
- Ship dark and 2x brand image variants so the old Meross logo is no longer
  used in dark mode or on high-DPI screens.

## 1.3.16

- Fix the 500 error when opening the initial configuration flow: mDNS
  discovery is best-effort and any discovery-stack failure now falls back to
  the manual broker form instead of aborting the flow.

## 1.3.15

- Fix remaining naming inconsistencies in logs and notices (**Meross Local
  Cloud**, **Meross Local Broker**).

## 1.3.14

- Rename the integration to **Meross Local Cloud** and make it local-only: the
  broker-selection step is gone and the config flow goes straight to the local
  broker. The official Meross cloud is no longer offered.
- Config labels now ask for the **local login** (a username is enough, no email
  required) and warn against using Meross cloud credentials.
- Fix compatibility with Home Assistant 2026.11: use `ATTR_COLOR_TEMP_KELVIN`
  and `color_temp_kelvin` instead of the removed mired-based color temperature
  API.
- Refresh the README/info and add the project banner and brand icon.

## 1.3.13

- Add roller-shutter calibration buttons using `Appliance.RollerShutter.Adjust`:
  start auto-calibration (`value=1`) and abort/stop (`value=0`). The command
  uses a raw namespace string because `meross_iot` 0.4.9.2 has no
  `ROLLER_SHUTTER_ADJUST` enum member.
- Add a **Calibration status** diagnostic sensor. After a start it polls `GET
  Appliance.RollerShutter.Adjust` every 15 s for 2 min, following a 90 s
  delay (the app's first poll); otherwise it polls every 5 min. It reports
  `success`, `timeout`, `motor_blocked` or `failed_N`. Incoming Adjust pushes
  are not visible through `meross_iot` 0.4.9.2, hence polling.
- Add Home Assistant runtime tests (`tests/`, 12 cases) covering entity
  creation, command payloads, status mapping and monitoring.

## 1.3.12

- Add roller-shutter open/close duration number entities (`signalOpen`/`signalClose`) for MRS100-class covers.
- These entities work with the local broker add-on's persisted/replayed timing config.

## 1.3.11

- Fork for MRS100 / local Meross broker use.
- Roller-shutter cover support through the local broker abilities and the existing `RollerShutterTimerMixin`.
- Distribution via HACS custom repository.

# 1.3.10beta1 (2025-09-29)
- Update low-level dependency to 0.4.9.2, so to address #569
- Attempt to address #479

# 1.3.9 (2025-08-22)
- Address #563: let HA re-authenticate in case of expired token or password change

# 1.3.8 (2025-08-22)
- Address #552, #568 and similar.

# 1.3.7 (2025-06-18)
- Merge #555 to fix config_entries.async_forward_entry_setup deprecation (thanks @Easen!)

# 1.3.6 (2025-03-17)
- Updated meross_iot dependency to 0.4.9.0 which fixes issues with paho-mqtt
- Set Min HA version to 2025.3

# 1.3.5 & 1.3.4 - RETIRED

# 1.3.2beta1 (2024-05-04)
- Using MerossIot v0.4.7.2b3 which should add support for HomeKit Hubs (addressing #435 and possibly #400)
- Add support for BatteryLevel sensors for Meross SubDevices
- Address #499

# 1.3.1 (2024-04-28)
- Fix light platform deprecations
- Fix climate platform deprecations
- Add OPENING and CLOSING transient states for garage openers (#493)
- Change log verbosity from INFO to DEBUG (addresses #481)

# 1.3.1beta1 (2024-04-25)
- Implement MFA support (addressing #467)
- Avoid storing username/password credentials (addressing #486)

<!--next-version-placeholder-->
# 1.3.0 (2024-04-25)
- Add support for Meross OilDiffuser
- Refactor Meross Humidifier
- Update low level library to version 0.4.7.0
- Addressing #484 

# 1.2.12 (2024-01-27)
- Merge PR #449, fixing #448. Credits to @mguilherme

# 1.2.11 (2024-01-27)
- Using the latest API Endpoints from Meross, version 0.4.6.0
- Fix logging errors
- Fix deprecated constants usage

# 1.2.10 (2023-10-15)
- Using the latest API Endpoints from Meross
- Supporting energy sensor for plugs (#460, thanks to @benoitm974)
- Fixes component unloading issue (thanks to @TheHolyRoger)
- Attention: this version is not compatible with local-only addon

# 1.2.9b0 (2023-09-18)
- Update low-level library to v0.4.6.0rc2 to support new API endpoints
- Merged PR #447

# 1.2.8 (2022-01-05)
- Update low-level library to v0.4.5.7, addressing issue #414

# 1.2.7 (2023-01-04)
- Update low-level library to v0.4.5.4 to solve issue #412

# 1.2.6 (2022-07-27)
- Add roller shutter (MSR100) support
- Add thermostat (MTS200) support
- Implement support for LAN-LOCAL HTTP transport mode
- Update dependency to low-level meross_iot library (0.4.5.0)

# 1.2.5rc5 (2022-06-24)
- Fix log error caused by wrong variable reference

# 1.2.5rc (2022-06-23)
- Set addon to run on internal network
- Set default values for IP:PORT when using local addon and no mDNS info is gathered.

# 1.2.5rc3 (2022-06-23)
- Set addon to run on host network to make mDNS work
- Improve setup & UI experience

# 1.2.5rc2 (2022-06-18)

- Fix import error preventing the component from loading via HA

# 1.2.5rc1 (2022-06-18) - RETIRED

- Removed zeroconf HA discovery support as it is now managed via setup config flow.
- This component is now working with the [Meross Local Addon](https://github.com/albertogeniola/ha-meross-local-broker) (still in alpha, though).

# 1.2.5rc0 (2022-06-12)

- Merges 1.2.4-rc1 features with the latest master release (v1.2.4)  

# 1.2.4 (2022-06-12)

- Merges pull request #365 that fixes MSS3XX consumption readings

## 1.2.4-rc1 (2022-06-06)

### Feature

- Updated low-level library to MerossIot v0.4.4.7

## 1.2.4-rc0 (2022-06-05)

### Feature

- Updated low-level library to MerossIot v0.4.4.6

## 1.2.3 (2022-06-03)

### Feature

- Updated low-level library to MerossIot v0.4.4.5

## 1.2.2 (2022-05-29)

### Feature

- Prepared component for integration with the Meross local-addon
- Updated HACS badge URL (thanks to @wrt54g)

## 1.2.1 (2022-01-30)

### Feature

- Upgraded low-level library dependency to 0.4.4.4
- Added MSG200 Support  
- Updated default polling intervals: sensor polling every 30s, API discovery every 120s
- Added option to set a custom user-agent for HTTP communication against Meross API


## 1.2.0rc2 (2022-01-18)

### Feature

- Upgraded low-level library dependency to 0.4.4.3
- Improved HACS documentation
- Added .devcontainer and .vscode tasks to support local-debugging
