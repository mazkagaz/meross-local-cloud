# Stratégie de test

## Niveaux

| Niveau | Portée | Emplacement |
|---|---|---|
| Unitaire | chemins, matching, compiler, runtime, scheduler, entités | `tests/test_profile_*.py`, `tests/test_broker_*.py` |
| Contrat | schémas et fixtures broker ↔ intégration | `tests/test_contracts.py`, `tests/contracts/` |
| Intégration HA | config flow, coordinator, diagnostics, réparations | `tests/test_*.py` |
| Fonctionnel H2 | bus MQTT en mémoire + simulateurs | `tests/functional/` |
| Matériel | toutes les familles du catalogue (MRS100 de référence, autres via testeurs) | `docs/testing/D5-VALIDATION.md` |

## Exécution

```bash
make test                 # suite complète
make test-fast            # unitaires + intégration
make test-functional      # scénarios H2
make test-contracts       # contrats
```

La CI exécute les suites rapides, les fonctionnels puis la suite complète, et
publie les rapports JUnit.

## Règles

- Chaque fonctionnalité couvre le cas standard et au moins un cas dégradé
  (timeout, erreur HTTP, signature invalide, appareil absent, payload malformé).
- Toute évolution de configuration ou de migration est testée.
- Les scénarios fonctionnels portent les IDs `F1`–`F8` lorsqu’ils existent.
- Les tests supprimés avec le legacy sont remplacés par la couverture profil
  équivalente, référencée dans la matrice.
- Aucun pourcentage de couverture n’est imposé à ce jour ; la traçabilité
  fonctionnelle fait foi.

## Hygiène

- Pas de mock du broker HTTP pour les tests de contrat.
- Les tests fonctionnels passent par le bus MQTT et les descriptors réels.
- Les identifiants, tokens et secrets de test ne doivent pas ressembler à des
  secrets de production.
- Les tests doivent rester indépendants de l’ordre d’exécution.
