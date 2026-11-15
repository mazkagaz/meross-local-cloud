# Modifications

- Fork date: 2026-11-13
- Upstream: https://github.com/albertogeniola/meross-homeassistant
- Upstream license: MIT
- Fork license: MIT (see `LICENSE`)
- Modifications copyright: 2026 the MRS100 fork contributors

## Branding

- Display name: **Meross Local Cloud**.
- Banner and logo: originals in `branding/`, generated brand assets in
  `custom_components/meross_cloud/brand/`.

## Changed files

| File | Change |
|---|---|
| `hacs.json` | Fork name; HACS custom-repository metadata |
| `custom_components/meross_cloud/manifest.json` | Fork name, documentation/issue URLs, codeowner placeholder, version 1.3.15; requirements unchanged (`meross_iot==0.4.9.2`) |
| `README.md`, `info.md` | Fork install/usage notes and attribution |
| `CHANGELOG.md` | 1.3.11-1.3.13 fork entries |
| `custom_components/meross_cloud/common.py` | Registered the `number` and `button` platforms |
| `custom_components/meross_cloud/number.py` | **New**: roller-shutter open/close duration entities |
| `custom_components/meross_cloud/button.py` | **New**: roller-shutter start/stop calibration buttons |
| `custom_components/meross_cloud/calibration.py` | **New**: raw `Appliance.RollerShutter.Adjust` send/GET helpers and status store |
| `custom_components/meross_cloud/sensor.py` | Adds the roller-shutter calibration status sensor |
| `pytest.ini`, `tests/` | **New**: Home Assistant runtime tests for the calibration button/sensor |

The fork now adds functional roller-shutter timing entities and calibration
buttons. MRS100 cover support still comes from the upstream
`RollerShutterTimerMixin` and the local broker abilities; the fork adds
`number.py`/`button.py` and registers those platforms.

Calibration is sent with the raw string namespace
`Appliance.RollerShutter.Adjust` because `meross_iot` 0.4.9.2's `Namespace`
enum lacks a member for it. The manager accepts raw namespace strings. The
library also drops incoming `Adjust` push notifications, so the status sensor
polls `GET Adjust` instead.

New files (`number.py`, `button.py`, `calibration.py`, `NOTICE`,
`MODIFICATIONS.md`, `LEGAL.md`, `configure.sh`, `push.sh`) are copyright 2026
the MRS100 fork contributors, MIT.
