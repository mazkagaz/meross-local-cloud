# Spécification — entités et identité

## Plateformes

| Plateforme | Source profil | Commandes |
|---|---|---|
| switch | `onoff` | turn_on/off |
| light | `onoff`, `brightness`, `rgb` | on/off, luminosité, RGB |
| sensor | `value` | — |
| binary_sensor | `value` | — |
| cover | `position` | open/close/stop/set_position ; `stop` est prioritaire, sans attente d’ACK ni rate-limit |
| number | `value` | set_value |
| button | — | press |
| climate | températures, `onoff`, `mode` | consigne, on/off |
| fan | `speed`, `max_speed` | vitesse, on/off |
| humidifier | `mode`/`onoff` | on/off |
| update | version du profil | reload de l’entrée |

## Identité

- `unique_id = <plateforme>:<device_internal_id>:<canal>[:classificateurs]`.
- Appareil principal : `#BASE:<uuid>`.
- Subdevice : `#BASE:<hub_uuid>#SUB:<subdevice_id>`.
- `via_device` du subdevice pointe vers `#BASE:<hub_uuid>`.
- Les entités update utilisent `meross_cloud:<uuid>:update:<profil>`.
- Au démarrage, les entités de la bêta 2.5 sans `#BASE:` sont supprimées ;
  les entrées historiques sont conservées.

## Disponibilité

Une entité est disponible si :

1. l’adapter est `connected` ;
2. le transport MQTT est connecté (si l’information existe) ;
3. l’appareil n’est pas explicitement `OFFLINE`.

Les mises à jour de disponibilité rafraîchissent l’état HA sans recréer
l’entité.

## Migration et rollback

- Aucun `entity_id` ni `unique_id` ne doit changer lors d’un reload.
- Les automatisations historiques doivent continuer à résoudre les entités.
- Le retour arrière vers 2.4.6 conserve le registre existant.

## Critères d’acceptation

- INT-ENT-001, INT-ID-001, INT-AVAIL-001.
- Tests : `test_profile_entities.py`, `test_d5_invariants.py`,
  `test_d5_migration.py`, `test_broker_adapter_availability.py`.
