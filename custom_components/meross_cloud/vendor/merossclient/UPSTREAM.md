# Vendored merossclient

- Upstream: https://github.com/krahabb/meross_lan
- Version: **v6.0.2**
- Commit: `f7783303269c7f2b021400ea369b7d150a773a63`
- License: MIT (see `LICENSE`)

## Included

`merossclient/__init__.py`, `protocol/`, `device/`, `client/__init__.py`,
`client/mqtt.py`, `library/`, `logging.py`, `exceptions.py`, `obfuscate.py`,
`broadcast.py`.

## Excluded

`cloudapi.py`, `client/bluetooth.py`, `client/http.py` (Meross cloud/BLE/HTTP
direct), HA integration layer (`helpers/`, `devices/`, `config_flow.py`).

## Local modifications

- `from __future__ import annotations` added to the vendored modules so they
  import on Python 3.13 (upstream v6.0.2 relies on Python 3.14 lazy
  annotations).
- `devices.json` is loaded lazily through `get_devices_library()` instead of at
  import time: Home Assistant rejects blocking file I/O on the event loop.
- The upstream `MEROSSDEBUG` block no longer reads `debug.secret.json` at
  import; the vendored copy uses an empty debug configuration.
- No behavioural change otherwise.

## Updating

1. Check out the target upstream tag/commit.
2. Replace the included paths, reapply the future-import patch.
3. Run the integration test suite and the D1 transport tests.
4. Update this file (version/commit) and `NOTICE` if the license changes.
