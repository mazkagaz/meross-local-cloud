# ADR-0002 — Identité historique

## Statut

Accepté — D5-c.

## Contexte

Les premières entités avaient des IDs construits avec l’identifiant interne
complet (`#BASE:<uuid>`), tandis que la bêta profil utilisait l’UUID brut. Deux
entrées de registre pouvaient coexister.

## Décision

- `unique_id = plateforme:device_internal_id:canal[:classificateurs]`.
- Appareil : `#BASE:<uuid>` ; subdevice : `#BASE:<hub>#SUB:<id>`.
- Les entités de la bêta 2.5 sans `#BASE:` sont supprimées au démarrage.
- Les entrées historiques sont réutilisées.

## Conséquences

- Les automatisations et l’historique d’entité restent attachés aux mêmes IDs.
- L’historique HA n’est pas migré si l’utilisateur l’a déjà abandonné.
- Toute nouvelle plateforme doit définir ses classificateurs historiques.
