# Test de bout en bout — Home Assistant Container + broker autonome

Ce test valide l'intégration réelle (pas un mock) contre un broker en mode
autonome, dans une instance **Home Assistant Container** jetable. Il vit dans
le dépôt broker : `tests/docker/`.

## Outils requis

- Docker accessible à l'utilisateur (groupe `docker`, ou `sg docker -c '…'`).
- `curl`.
- Python 3.11+ avec `aiohttp` pour piloter HA (le venv de test de
  l'intégration convient : `HA_PYTHON=/chemin/.ha-venv/bin/python`).
- Les images `ghcr.io/mazkagaz/amd64-meross_local_broker:1.4.8` (ou
  `aarch64`) et `ghcr.io/home-assistant/home-assistant:stable`.
- Le dépôt intégration à côté du dépôt broker (ou `CLOUD_ROOT`).

## Valeurs de test

| Élément | Valeur |
|---|---|
| Compte local broker | `local-user` / `secret` |
| Compte HA | `e2e` / `e2e-pass-123` (créé au premier lancement) |
| Broker pour l'intégration | `127.0.0.1`, HTTPS 2004, MQTT 2001 |
| Admin broker | `0.0.0.0:2003`, CIDR Docker `172.16.0.0/12` |
| SAN TLS | `127.0.0.1` |
| Réseau | HA partage le namespace du broker (`--network container:`) |

Ces identifiants sont strictement réservés aux tests.

## Lancer

Depuis le dépôt broker :

```bash
CLOUD_ROOT=/chemin/meross-cloud \
HA_PYTHON=/chemin/meross/.ha-venv/bin/python \
bash tests/docker/run.sh
```

Détails des variables, du nettoyage et du dépannage :
`../meross-local-broker/tests/docker/README.md`.

## Ce qui est vérifié

- démarrage du broker autonome (HTTPS, admin, MQTT/TLS, génération du CA) ;
- création du compte local via l'API admin ;
- onboarding HA et ajout de l'entrée par le **flux de configuration réel** ;
- entrée `meross_local_cloud` à l'état `loaded` ;
- événements broker : login « Meross Local API » et login applicatif ;
- absence d'avertissement HA `Detected blocking call … meross_local_cloud`
  (régression de l'import paho exécuté sur la boucle d'événements).

## Limites

- Aucun appareil Meross ni pairer : l'appairage et les commandes device ne
  sont pas couverts.
- L'image HA `stable` évolue ; relancer le test après une montée de version
  majeure de HA.
- Le test ne remplace pas les tests unitaires/fonctionnels ni les essais
  matériels.

## Dépannage

| Symptôme | Vérifier |
|---|---|
| `permission denied` Docker | groupe `docker` ou `sg docker -c` |
| Port occupé | conteneurs de test précédents |
| Entrée en `setup_error` | logs HA, logs broker, compte local |
| CA refusé | SAN, `127.0.0.1`, redémarrage après changement d'IP |
| Test bloqué au démarrage HA | `default_config`, logs `e2e-ha-t` |
