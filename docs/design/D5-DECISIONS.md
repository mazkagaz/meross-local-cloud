# Décisions de conception D5

## Lots

| Lot | Décision | Livrable |
|---|---|---|
| D5-a | Invariants de dépendance et d’identité | tests garde-fous |
| D5-b | Authentification et transport portés par le coordinator/adapter | suppression du manager |
| D5-c | Identité historique et parité volet | IDs `#BASE`, P3, calibration |
| D5-d | Suppression de `meross_iot` et des plateformes legacy | `paho-mqtt` seul |
| D5-e | Réparations appareil sans profil et états dégradés | hardening |
| D5-f | Pré-releases 3.0.0-beta.x et checklist de validation | release |

## ADR

- [ADR-0001 — Backend profils obligatoire](ADR-0001-profile-only.md)
- [ADR-0002 — Identité historique](ADR-0002-historical-identity.md)
- [ADR-0003 — Transport et disponibilité](ADR-0003-transport-availability.md)

## Conséquences

- Le catalogue broker devient le point d’extension des familles d’appareils.
- Une famille absente ne produit aucune entité, mais une réparation explicite.
- Les automatisations historiques sont préservées par les IDs.
- Le retour arrière vers 2.4.6 reste possible via HACS.
