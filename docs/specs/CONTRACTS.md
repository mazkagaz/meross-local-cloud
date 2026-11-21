# Contrats broker

L’intégration consomme les contrats API versionnés du dépôt broker.

- Version : **1**.
- Objets : `signIn`, `devList`, `profiles/rev`, `profiles`, `profiles/pubkey`,
  `rollerShutterConfig`.
- Copie locale : `tests/contracts/*.json` et `tests/contracts/fixtures/*.json`.
- Test de dérive : `tests/test_contracts.py` compare les fichiers au checkout
  broker épinglé dans la CI.

Référence normative :
[broker/docs/specs/API-CONTRACTS.md](https://github.com/mazkagaz/meross-local-broker/blob/main/docs/specs/API-CONTRACTS.md).

## Règle de changement

Tout changement cassant exige une nouvelle version de contrat et une release
coordonnée des deux dépôts. Les ajouts compatibles restent optionnels.

## Critère d’acceptation

- INT-CONTRACT-001 : schémas et fixtures identiques, validation des réponses
  simulées.
