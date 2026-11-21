# Architecture de l’intégration

## Rôle

Traduire le catalogue de profils du broker local et les trames MQTT des
appareils en entités Home Assistant. Depuis la 3.0, l’intégration est
**profile-only** : elle ne contient plus de modèle d’appareil historique ni
`meross_iot`.

## Composants

| Composant | Fichier | Responsabilité |
|---|---|---|
| Config flow | `config_flow.py` | découverte mDNS, login HTTPS, CA, réauthentification |
| Coordinator | `__init__.py` | token, `devList`, TLS, suivi des appareils absents |
| Transport MQTT | `broker_transport.py` | une connexion applicative, requêtes, ACK, pushes |
| Client HTTP | `broker_http.py` | enveloppe signée, login, contrats API |
| Adapter profils | `broker_adapter.py` | catalogue, matching, runtimes, scheduler, réparations |
| Compilateur | `profiles/` | schéma, chemins, matching, runtime, scheduler |
| Entités | `profile_entities.py` | plateformes HA, identités, commandes, disponibilité |
| Réparations | `missing_devices.py`, `repairs.py` | absence 48 h, Unbind, appareil sans profil |
| Diagnostics | `diagnostics.py` | état TLS, appareils, catalogue, compteurs |

## Flux

```text
HA config entry
  └─ coordinator : HTTPS signé /signIn, /devList
       └─ adapter : /profiles/rev, /profiles, /profiles/pubkey
            ├─ vérification Ed25519
            ├─ MQTT describe(System.All/Ability)
            ├─ match + compile + DeviceRuntime
            ├─ DeviceScheduler (un par appareil)
            └─ profils → entités HA
```

## Invariants

- Une seule connexion MQTT applicative par entrée de configuration.
- Le catalogue broker est la seule source des appareils et des entités.
- Les `unique_id` et identifiants d’appareil historiques sont conservés.
- La disponibilité combine `devList`, pushes `Online` et état du transport.
- Un appareil sans profil ne crée pas d’entité et déclenche une réparation.
- Les commandes passent par le runtime et rafraîchissent le namespace concerné.
- Aucun secret n’est écrit en clair dans les diagnostics ou les logs.

## Documentation liée

- [Spécification du backend](../specs/BACKEND-PROFILE.md)
- [Entités et identité](../specs/ENTITIES-IDENTITY.md)
- [Traçabilité](../testing/TRACEABILITY.md)
