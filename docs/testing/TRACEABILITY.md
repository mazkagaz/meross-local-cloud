# Matrice de traçabilité — intégration

Exigences → spécification → décision → code → tests.

| ID | Exigence | Spécification | ADR | Code | Tests unitaires / intégration | Fonctionnel / manuel |
|---|---|---|---|---|---|---|
| INT-AUTH-001 | Login HTTPS, token, réauthentification | BACKEND-PROFILE | ADR-0003 | `__init__.py`, `broker_http.py`, `config_flow.py` | `test_d5_auth.py`, `test_broker_http.py`, `test_coordinator_discovery.py`, `test_config_flow.py` | F1 |
| INT-CAT-001 | Catalogue signé, révision, reload | BACKEND-PROFILE | ADR-0001 | `broker_adapter.py`, `broker_profiles.py` | `test_broker_profiles_adapter.py` | F6 |
| INT-MATCH-001 | Matching type/MAC/abilities/ambiguïtés | BACKEND-PROFILE | ADR-0001 | `profiles/match.py`, `profiles/registry.py` | `test_profile_match.py`, `test_profile_registry.py` | F3 |
| INT-RUNTIME-001 | Chemins, échelles, dispatch, erreurs | BACKEND-PROFILE | ADR-0001 | `profiles/paths.py`, `profiles/compiler.py`, `profiles/runtime.py` | `test_profile_paths.py`, `test_profile_compiler.py`, `test_profile_runtime.py`, `test_profile_engine_purity.py` | F3, F7 |
| INT-SCHED-001 | Batching, lazy refresh, ACK unique, backoff | BACKEND-PROFILE | ADR-0003 | `profiles/scheduler.py`, `broker_transport.py` | `test_profile_scheduler.py` | F4, F5 |
| INT-ENT-001 | Mapping des plateformes et commandes | ENTITIES-IDENTITY | ADR-0001 | `profile_entities.py` | `test_profile_entities.py`, `test_profile_parity.py` | F3 |
| INT-ID-001 | IDs historiques et migration bêta | ENTITIES-IDENTITY | ADR-0002 | `common.py`, `profile_entities.py`, `__init__.py` | `test_d5_invariants.py`, `test_d5_migration.py` | F2, validation 3.0 |
| INT-AVAIL-001 | devList, Online, transport | ENTITIES-IDENTITY | ADR-0003 | `broker_adapter.py`, `broker_transport.py` | `test_broker_adapter_availability.py` | F2, F7 |
| INT-REPAIR-001 | Absence 48 h, Unbind, sans profil | CONFIG-REPAIRS | ADR-0003 | `missing_devices.py`, `repairs.py`, `broker_adapter.py` | `test_missing_devices.py`, `test_repairs.py`, `test_d5_hardening_functional.py` | F7 |
| INT-CFG-001 | Config flow, options, reload | CONFIG-REPAIRS | — | `config_flow.py`, `__init__.py` | `test_config_flow.py` | F1 |
| INT-DIAG-001 | Diagnostics expurgés et résumé profils | SECURITY-DIAGNOSTICS | — | `diagnostics.py` | `test_diagnostics.py` | F1 |
| INT-SEC-001 | TLS, redaction, secrets | SECURITY-DIAGNOSTICS | — | `tls.py`, `log_redaction.py`, `broker_http.py` | `test_setup_tls.py`, `test_tls.py`, `test_log_redaction.py` | F7 |
| INT-CONTRACT-001 | Contrats broker sans dérive | CONTRACTS | — | `broker_devices.py`, `broker_profiles.py`, `broker_config.py` | `test_contracts.py` | F6 |
| INT-FUNC-001 | Familles réelles sur bus MQTT | BACKEND-PROFILE | ADR-0001 | profils + adapter | `tests/functional/*` | F3, F4, F5 |
| INT-REL-001 | Bêta et rollback | D5-VALIDATION | ADR-0001 | métadonnées, docs | `test_d5_invariants.py` | manuel |

## Couverture fonctionnelle

| Scénario | Tests |
|---|---|
| F2 identité/disponibilité | `functional/test_d5_cutover_functional.py` |
| F3 MRS100 | `functional/test_mrs100_functional.py` |
| F3 MSS310, hub, MTS200, lumière, diffuseur | `functional/test_mqtt_bus_functional.py`, `functional/test_simulated_families_functional.py` |
| F4/F5 scheduler et ACK | `functional/test_scheduler_ack_functional.py` |
| F7 hardening et réparations | `functional/test_d5_hardening_functional.py` |

## Couverture non automatisée

| Élément | Validation |
|---|---|
| MRS100 réel, calibration et durées | checklist `D5-VALIDATION.md` |
| Automatisations historiques | vérification manuelle après installation |
| Rollback HACS vers 2.4.6 | procédure manuelle |
| Familles non couvertes par le catalogue | réparation « appareil sans profil » |
