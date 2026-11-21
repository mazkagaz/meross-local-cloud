# ADR-0001 — Backend profils obligatoire

## Statut

Accepté — intégration 3.0.

## Contexte

Le backend historique `meross_iot` gérait les appareils par mixins et imposait
des patches pour les ACK, le TLS et les lumières. Le catalogue de profils
permet d’ajouter une famille sans publier d’intégration.

## Décision

- Le catalogue broker et les descriptors MQTT sont l’unique source des
  appareils et des entités.
- `MerossManager`, `MerossDevice`, `calibration.py`, `patches.py` et les
  plateformes historiques sont supprimés.
- `paho-mqtt==2.1.0` est la seule dépendance runtime.
- Un appareil sans profil ne crée aucune entité et déclenche une réparation.

## Conséquences

- Les fonctions absentes du catalogue disparaissent jusqu’à l’ajout du profil.
- Les évolutions d’appareils se font côté broker, sans release HACS.
- Le retour arrière impose la réinstallation de 2.4.6.
