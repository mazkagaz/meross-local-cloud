# Modifications

- Fork date: 2026-11-13
- Upstream: https://github.com/albertogeniola/meross-homeassistant
- Upstream license: MIT
- Fork license: MIT (see `LICENSE`)
- Modifications copyright: 2026 the MRS100 fork contributors

## Branding

- Display name: **Meross Local Cloud**.
- Banner and logo: unified originals in `branding/` (the logo is a transparent
  PNG); generated brand assets in `custom_components/meross_local_cloud/brand/`.

## Vendored code

`custom_components/meross_local_cloud/vendor/merossclient/` contains a restricted
copy of meross_lan v6.0.2 (`f778330`), MIT. Only the protocol, descriptor,
device, library, logging and MQTT client modules are included; cloud, BLE and
direct-HTTP modules are excluded. The only local change is the addition of
`from __future__ import annotations` so the code runs on Python 3.13. See
`vendor/merossclient/UPSTREAM.md` and `NOTICE`.

## Changed files

| File | Change |
|---|---|
| `hacs.json` | Fork name; HACS custom-repository metadata |
| `custom_components/meross_local_cloud/manifest.json` | Fork name, URLs, version 3.0.0-beta.1; requirement `paho-mqtt==2.1.0` |
| `README.md`, `info.md` | Profile-only install/usage notes and attribution |
| `CHANGELOG.md` | Fork entries up to 3.0.0-beta.1 |
| `custom_components/meross_local_cloud/broker_adapter.py` | **New**: catalog verification, matching, runtimes, schedulers, availability and repairs |
| `custom_components/meross_local_cloud/broker_http.py` | **New**: signed local-broker HTTP client |
| `custom_components/meross_local_cloud/broker_transport.py` | **New**: MQTT transport over the vendored merossclient |
| `custom_components/meross_local_cloud/profiles/` | **New**: declarative profile compiler, runtime and scheduler |
| `custom_components/meross_local_cloud/profile_entities.py` | **New**: profile-driven HA entities with historical identifiers |
| `custom_components/meross_local_cloud/*.py` platforms | Reduced to profile entity setup |
| `custom_components/meross_local_cloud/missing_devices.py`, `repairs.py` | Missing-device tracking, Unbind and unsupported-profile repairs |
| `pytest.ini`, `tests/` | Unit, contract and H2 functional suites, including in-memory MQTT simulators |

The fork now drives every entity from the broker profile catalog. The
integration no longer embeds `meross_iot`, its manager or its monkey patches;
`paho-mqtt` is the only runtime dependency. Roller-shutter durations,
calibration status and profile update entities are described by the catalog
and rendered by the profile entity layer.

Files added by the fork are copyright 2026 the MRS100 fork contributors, MIT.
