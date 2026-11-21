# Spécification — backend profils

## Objectif

Construire les appareils et leurs entités uniquement depuis le catalogue signé
du broker et les descriptors MQTT.

## Catalogue

- Endpoints : `/v1/Device/profiles/rev`, `/profiles`, `/profiles/pubkey`.
- La révision et le nombre de profils sont lus avant le catalogue.
- Si `signature` est présent, la clé publique est récupérée et la signature
  Ed25519 vérifiée. Une signature absente est signalée `absent` ; une signature
  invalide met l’adapter en erreur et interdit la création d’entités.
- La révision surveillée toutes les 60 s ; un changement recharge l’entrée.

## Découverte et matching

- `devList` fournit l’UUID, le type, le sous-type et l’état en ligne.
- Le descriptor MQTT fournit le type, le firmware, les abilities, la MAC et les
  subdevices.
- Le matching applique : MAC + sous-type, sous-type, type/abilities exacts,
  préfixe le plus long, puis `*`.
- Une ambiguïté est comptée ; un appareil sans profil est signalé par une
  réparation et ne crée aucune entité.

## Runtime et scheduler

- Un `DeviceRuntime` par appareil, un `DeviceScheduler` par appareil.
- Le scheduler regroupe les GET dans `Appliance.Control.Multiple`, applique un
  rate-limit et un backoff en échec.
- Les pushes sont routés vers le runtime ; un ACK sollicité n’est jamais
  dispatché deux fois.
- Les commandes passent par le transport puis rafraîchissent le namespace.

## États dégradés

| Cas | Comportement |
|---|---|
| HTTP broker indisponible | `ConfigEntryNotReady`, retry |
| token invalide | `ConfigEntryAuthFailed` |
| catalogue indisponible | adapter en `error`, aucune entité |
| signature invalide | catalogue refusé |
| MQTT indisponible | adapter en `error` ou entités indisponibles |
| appareil hors ligne | entités indisponibles, retour automatique |
| nouveau device | reload automatique de l’entrée |

## Critères d’acceptation

- INT-CAT-001, INT-MATCH-001, INT-RUNTIME-001, INT-SCHED-001.
- Tests unitaires et fonctionnels correspondants dans
  [TRACEABILITY](../testing/TRACEABILITY.md).
