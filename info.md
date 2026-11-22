**English** · [Français](info.fr.md)

# Meross Local Cloud — local broker (fork)

![Meross Local Cloud](branding/meross-local-cloud-banner.jpeg)

Unofficial Home Assistant integration to control Meross devices paired to a
**local broker**, without the Meross cloud in daily use. Only local mode is
supported: no official cloud credentials are used.

## Quick install

1. First install the
   [Meross Local Broker](https://github.com/mazkagaz/meross-local-broker) add-on.
2. Pair the device with
   [Meross Local Pairer](https://github.com/mazkagaz/meross-local-pairer).
3. In HACS: **Integrations → ⋮ → Custom repositories**, add
   `https://github.com/mazkagaz/meross-local-cloud` with category **Integration**.
4. Download the integration and restart Home Assistant.
5. **Settings → Devices & services → Add integration → Meross Local Cloud**,
   then enter:
   - broker address: host or IP (pre-filled when the broker is discovered);
   - HTTPS: `2004`, MQTT: `2001`;
   - the add-on's **local login** (a username is enough, it does not have to be
     an email address).

Do not use official Meross cloud credentials: the integration only contacts the
local broker. Broker **1.2.1** and TLS are required.

## What the fork brings

- a backend fully driven by the broker's device profiles, without `meross_iot`;
- a signed profile catalog, a central scheduler and per-device availability;
- `number` entities for open/close durations, a Position slider, calibration
  buttons and a calibration status sensor;
- repairs for missing, unbound or profile-less devices.

The detailed procedure, entities and troubleshooting are in the
[README](https://github.com/mazkagaz/meross-local-cloud#readme).

## License

MIT. Unofficial fork of
[albertogeniola/meross-homeassistant](https://github.com/albertogeniola/meross-homeassistant);
attribution kept in `LICENSE`, `NOTICE` and `MODIFICATIONS.md`.
