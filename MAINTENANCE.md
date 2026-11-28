# Maintenance — Meross Local Cloud

Dernière revue : **2026-11-27**

## Politique de support

- **PR** : la CI teste la version de Home Assistant épinglée dans
  `tests/requirements_test.txt`.
- **Compatibilité** : un workflow planifié teste chaque semaine la dernière
  version de Home Assistant supportée par le dernier
  `pytest-homeassistant-custom-component` stable.
- **Minimum déclaré** : Home Assistant `2025.6`. Cette version minimale doit
  être couverte par un job dédié lors de la phase 1 de maintenance ; jusque-là,
  elle n’est pas une garantie testée.
- **Intégration broker** : la CI vérifie les contrats contre un commit broker
  épinglé. Le pin doit être mis à jour à chaque release broker.

## Rythme

| Fréquence | Action |
|---|---|
| Chaque PR | tests unitaires, fonctionnels, HACS, Hassfest, traductions, couverture ≥ 85 % |
| Hebdomadaire | compatibilité dernière HA stable + audit de sécurité runtime |
| Mensuel | revue des PR Dependabot, versions mineures et correctifs ; vérifier que pytest/pytest-cov restent fournis par le harness HA |
| Trimestriel | revue HA/Python, matrice de support, dépendances EOL |
| Annuel | revue d’architecture et de sécurité plus profonde |

## Automatisations

- `Dependabot` : dépendances Python de test et GitHub Actions, PR groupées.
- `maintenance.yaml` : compatibilité avec la dernière HA supportée et audit `pip-audit` de la dépendance runtime.
- `docs/operations/RELEASING.md` : procédure de release.

## Checklist de release

- [ ] La CI de la branche est verte.
- [ ] Le manifest et le tag vont porter la même version.
- [ ] `CHANGELOG.md` contient l’entrée de version.
- [ ] Le README EN/FR et `docs/translations.json` sont à jour.
- [ ] Les pins broker/intégration sont cohérents avec les versions publiées.
- [ ] Les images broker et le tag d’intégration sont testés.
- [ ] Aucun bump de version n’est poussé avant le commit final de release.
- [ ] Le commentaire d’issue ou de release décrit cause, correctif et version.

## Règles de conception

- Toute nouvelle famille d’appareil doit avoir un test unitaire ou golden frame
  et, si possible, un test fonctionnel sur le bus simulé.
- Tout correctif de compatibilité HA doit être couvert par un test ou par le
  workflow de compatibilité planifié.
- Les changements risqués passent par un flag ou un mode progressif.
- Les dépendances restent épinglées ; les montées majeures sont des PR dédiées.
- Un audit ponctuel ne remplace pas un gate CI : chaque constat doit devenir un
  test, un contrôle ou une checklist.
