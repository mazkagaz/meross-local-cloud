## 1.5.3

- Evaluate the server certificate SANs even when the stored skip option is
  true, so hostname verification is enabled as soon as the broker CA is
  trusted. Previously the skip flag prevented the SAN lookup and left
  `ca_check_hostname` false.

## 1.5.2

- Add diagnostics support: the downloaded diagnostics include the integration
  and meross_iot versions, the entry settings, the broker CA state (validity,
  fingerprint, SAN hostnames, hostname verification) and the device list.
  Tokens, keys and passwords are redacted.

## 1.5.1

- Declare the integration logger in the manifest so the Home Assistant log
  page filtered on Meross Local Cloud shows its messages.
- Log an unconditional INFO line at setup with the integration version, the
  pinned CA fingerprint and whether hostname verification is enabled.

## 1.5.0

- Trust the broker CA for HTTP and MQTT. The CA is downloaded from `/ca.crt`,
  validated (`CA:TRUE`) and pinned by SHA-256 in the config entry; a change is
  logged and the new CA is trusted automatically.
- HTTP and MQTT TLS contexts are built from that CA, with hostname
  verification enabled when the server certificate covers the configured host
  (the broker now publishes LAN IP SANs).
- The silent fallback to disabled verification is removed. When a valid CA is
  available it is used even if the old skip option is stored; the skip option
  remains a fallback for brokers without a valid CA.

## 1.4.23

- Revert 1.4.22: turning on the panel light no longer modifies the DND mode.
  This restores the meross_lan-aligned behavior of 1.4.21, with the ACK
  handling fix from 1.4.20.

## 1.4.22 (reverted in 1.4.23)

- Turning on the MRS100 panel light now disables Do Not Disturb first (mode
  `DND_DISABLED`) and waits briefly before sending the light command. DND
  gates the panel LEDs, so the light command was ignored while it was enabled
  — matching the manual sequence of toggling both entities that occasionally
  worked.

## 1.4.21

- Move the MRS100 light/DND diagnostics back to DEBUG. They were raised to
  INFO only to bypass the logger configuration while troubleshooting.

## 1.4.20

- Accept command ACKs delivered on `/app/<userId>/subscribe`. The broker agent
  forwards every device publish there, including GETACK/SETACK replies;
  meross_iot only matched ACKs on the app-specific response topic, so those
  replies were ignored and commands timed out (System.All, DNDMode, light).

## 1.4.19

- Align the MRS100 light entity with meross_lan: a plain on/off sends
  `Appliance.Control.Light` with only `channel` and `onoff`; luminance and the
  luminance capacity are added only when an actual brightness is requested.
  The entity state still follows the light digest and the last command.

## 1.4.18

- Light and DND diagnostics are logged at INFO, so they appear without any
  logger configuration. The setup line carries the integration version.

## 1.4.17

- More debug diagnostics for the MRS100 light: the cover light SET payload,
  acknowledgment and error, plus the raw light status and DND mode reads and
  writes. No behavior change.

## 1.4.16

- Drive the light of roller shutters and garage openers (MRS100) through
  `Appliance.Control.Light` instead of ToggleX, like meross_lan does: the
  ToggleX payload reported by covers is not standard and its state follows
  the motor activity. Turn-on sends `onoff=1` with a non-zero luminance and
  the luminance capacity; turn-off sends `onoff=0`. The light state prefers
  the light digest and falls back to the last command.

## 1.4.15

- Add debug diagnostics for MRS100 lights: the device abilities, whether it is
  ToggleX-controlled, the light state and the brightness on each turn on/off.
  No behavior change.

## 1.4.14

- Fix turning the MRS100 backlight back on. The light wrapper skipped the
  command when it believed the light was already on (some devices keep
  reporting `onoff=1`), and meross_iot then sent nothing. The turn-on command
  is now always sent; for non-toggle devices an explicit luminance is added
  so the `Appliance.Control.Light` payload is actually emitted.

## 1.4.13

- Light entities now expose Home Assistant-valid color modes: a
  brightness-only device uses `ColorMode.BRIGHTNESS` instead of `WHITE`
  (which the entity registry rejects), and the active mode always belongs to
  the supported set.
- Startup and reconnect log noise removed: `CommandTimeoutError` during
  device, power or DND updates is logged at debug level instead of a full
  traceback, and the last known state is kept.

## 1.4.12

- Build the MQTT TLS context in an executor and hand it to paho through
  `tls_set_context`. This removes Home Assistant's
  `Detected blocking call to load_verify_locations` warning emitted on every
  setup; verification and skip-validation modes are unchanged.

## 1.4.11

- Fix login against the broker HTTPS listener. `meross_iot` posts to
  `/v1/log/user` using the domain returned by the broker; the broker derives
  that domain from its nginx backend scheme and reports `http://…:2004`,
  which nginx rejects with HTTP 400. The login test now uses `async_login`
  and forces the configured endpoint, and stored credentials are migrated to
  it at setup.
- The simple form explains that **Advanced settings** must be checked and
  submitted to edit the endpoint, ports or TLS options.

## 1.4.10

- When no broker is discovered, the setup flow now opens the explicit
  endpoint/TLS form directly instead of showing a mode switch whose effect
  was invisible. The explicit form is also used when mDNS announces a service
  that cannot be resolved.
- When no mDNS service is found at all, probe the Home Assistant host's local
  IPv4 addresses on the default API ports (HTTPS 2004, then HTTP 2003).
- Restore the simple **Advanced settings** checkbox on the detected-broker
  form.

## 1.4.9

- When an mDNS service is announced but resolves without SRV/TXT/A records,
  the integration now probes the Home Assistant host's local IPv4 addresses
  on the API ports instead of giving up. This covers the add-on topology where
  the broker runs on the same host.
- When the TXT `https_port` record is missing (incomplete resolution), probe
  the broker default HTTPS port 2004 instead of assuming HTTPS is disabled.
- Extend the mDNS resolution timeout and log the probed candidates.

## 1.4.8

- Replace the **Advanced settings** checkbox with an explicit **Setup mode**
  selector: `Simple setup` or `Advanced settings (<version>)`. The option
  label comes from the integration code, not translations, so the running
  version is visible directly in the form. Select the advanced option and
  validate to open the explicit endpoint/TLS fields, even with empty values.
- Field label renamed to **Setup mode** in English, Spanish and Italian.

## 1.4.7

- The setup form now shows the running integration version and the detected
  broker, making it possible to confirm which code Home Assistant loaded
  without reading logs.
- Setup start, discovery results and the switch to advanced settings are
  logged at INFO.

## 1.4.6

- Discovery also probes the mDNS A/AAAA addresses, so a broker that does not
  publish the TXT `host` entry can still be found. IPv6 literals are formatted
  correctly in the derived URLs.
- The simple form no longer blocks submission when the broker address or the
  credentials are empty, so **Advanced settings** can be ticked and validated
  to reach the explicit fields. Missing values now return dedicated
  `missing_broker_host` / `missing_credentials` errors.
- The broker address accepts a pasted URL and keeps only its host.
- README: direct **Add to HACS** link.

## 1.4.5

- Automatic broker discovery now reads the add-on's mDNS TXT records
  (`host`, `http_port`, `https_port`) and probes HTTPS before HTTP, so the
  integration no longer assumes `homeassistant.local`.
- New simple setup: when a broker is discovered, only the local login and
  password are requested. Otherwise the Home Assistant host or IP and an
  HTTPS toggle are requested.
- Explicit endpoints, MQTT address and TLS options remain available under
  **Advanced settings**.
- A pasted address such as `http://10.0.0.5:2003/ca.crt` is reduced to its
  host before the endpoint is built.
- Reauthentication uses the same simple form and keeps the stored endpoints
  and TLS options.
- Spanish and Italian translations updated for the new flow.

## 1.4.4

- Climate entities use `native_temperature_unit`, `native_current_temperature`
  and `native_target_temperature`, removing Home Assistant's deprecation
  warnings.

## 1.4.3

- Replace the CA-chain verification introduced in 1.4.2: the CA generated by
  current brokers is not a valid CA (`basicConstraints` missing), so chain
  verification failed. When MQTT verification is enabled but the broker
  certificate cannot be verified, the integration now retries with validation
  disabled for the local broker and logs an explicit warning. Check
  "Skip MQTT certificate validation" to make that choice permanent.
- Keep the explicit CA bundle passed to paho, which avoids Home Assistant's
  blocking `load_default_certs` warning.
- Startup summary remains at INFO with the upstream project link.

## 1.4.2

- Verify the broker certificate chain with the CA served at `/ca.crt` for
  both HTTP and MQTT. Hostname matching is skipped because the local
  certificate may not contain the LAN IP. Existing entries fetch the CA during
  setup.
- Fall back to the configured skip options when the CA cannot be retrieved.
- Avoid Home Assistant's blocking `load_default_certs` warning by passing an
  explicit CA bundle to paho.
- Log the startup summary at INFO instead of WARNING and link the upstream
  project.
- Consume the broker's integer `bindTime`, removing the `meross_iot` warning
  for every device.

## 1.4.1

- Reauthentication now reuses the existing broker configuration: HTTP API
  endpoint, MQTT address and TLS options are prefilled, and the existing entry
  is updated in place instead of creating a duplicate when the endpoint changes.
- The reauthentication flow no longer resets the endpoint to
  `homeassistant.local:2003`.

## 1.4.0

- Support the broker HTTPS listener (`https://…:2004`, broker `alpha71`).
  The login step and every later HTTP call now accept the broker's
  self-signed certificate.
- New login option **Skip HTTP certificate validation**, opt-in and disabled
  by default. Check it only for the local broker's self-signed certificate;
  MQTT/TLS on port 2001 keeps its own skip option.
- The SSL error message now explains the option instead of suggesting plain
  HTTP only. Port 2003 remains available in plain HTTP.

## 1.3.22

- Fix every MRS100 entity update failing with `AttributeError: 'list' object
  has no attribute 'get'`. The pinned `meross_iot` release calls `.get()` on
  the default `light` digest even when the device has no light payload; a
  runtime patch now skips that mixin for non-light devices.
- Entity updates can no longer prevent an entity from being added when the
  third-party device update raises.

## 1.3.21

- Fix the 500 error when opening the integration options (gear icon):
  `OptionsFlow.config_entry` is now a read-only property in modern Home
  Assistant, so the flow must not assign it in its constructor.

## 1.3.20

- Keep entities available when the broker's HTTP device list reports a stale
  `offline`/`unknown` status (for example after a broker restart or when a
  second device is paired). The live MQTT state is now authoritative, and a
  failed HTTP poll no longer hides entities that MQTT still serves.

## 1.3.19

- Keep cover entities available when the HTTP device list transiently omits a
  device from a multi-device account: fall back to the MQTT online status
  instead of raising or marking the entity unavailable.

## 1.3.18

- Regenerate every icon from the transparent logo artwork (the JPEG source
  contained a checkerboard background).
- Set cover features through `_attr_supported_features` so open/close controls
  are exposed consistently, and log cover entity creation for diagnostics.

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
