**English** · [Français](MIGRATION-4.0.fr.md)

# Migrating to 4.0.0 — Home Assistant domain change

Version 4.0.0 changes the Home Assistant integration domain from
`meross_cloud` to `meross_local_cloud`. This is a **breaking change** for
existing installations: the old configuration entry, devices and entities are
not migrated automatically.

The broker and the pairer are unchanged. Only this integration must be removed
and added again.

## What changes

- The component directory becomes `custom_components/meross_local_cloud`.
- The configuration entry belongs to the new domain. The old `meross_cloud`
  entry becomes orphaned and must be removed.
- Devices and entities are recreated. Entity names usually produce the same
  `entity_id` when the old entities are removed first; verify your automations
  and dashboards.
- The integration runtime cache and the pending “missing device” state are not
  carried over. They rebuild automatically after the devices come back.
- The broker address, ports and local account are **not** migrated: enter them
  again when adding the new integration.

## Before you start

1. Note the important `entity_id`s and the automations/scripts/dashboards that
   use them.
2. Make a Home Assistant backup.
3. Keep the broker running; no broker change is required.

## Migration steps

1. In Home Assistant, open **Settings → Devices & services**.
2. Open the old **Meross Local Cloud** entry and delete it. This removes its
   devices and entities.
3. In **HACS → Integrations → Meross Local Cloud**, uninstall the 3.x version,
   or update it to 4.0.0.
4. Check the Home Assistant configuration directory: if
   `custom_components/meross_cloud` still exists, delete it. Only
   `custom_components/meross_local_cloud` must remain.
5. Restart Home Assistant.
6. Add the integration again: **Settings → Devices & services → Add
   integration → Meross Local Cloud**.
7. Enter the broker address, the HTTPS/MQTT ports and the local account, as
   during the first installation. The CA is fetched and pinned again.
8. Check that the devices and entities are back. Adjust automations or
   dashboards if an `entity_id` changed.

## HACS notes

HACS tracks the repository URL, not the integration domain. Updating from 3.x
to 4.0.0 therefore works, but the old component directory can remain on disk.
A clean uninstall/reinstall, or the manual deletion described above, avoids a
stale `custom_components/meross_cloud` folder.

## Rollback

To go back to 3.2.2, reinstall that version in HACS, remove the 4.0.0
configuration entry, delete `custom_components/meross_local_cloud`, restart and
add the integration again. The rollback is also manual.

## Troubleshooting

- **“Integration not found” or a setup error after updating**: the old
  `meross_cloud` entry is still present. Delete it, then add the new
  `meross_local_cloud` entry.
- **Entities duplicated or `_2` suffixes**: old entities were not removed
  before the new ones were created. Delete the old entry, remove the leftover
  entities, then add the integration again.
- **Automations no longer trigger**: check the entity IDs used by the
  automation. Device-based triggers may need the new device.
- **Statistics/history**: they are attached to the entity ID. If the same ID is
  reused, history usually continues; otherwise use the statistics editor to
  reassign the old statistic ID.
