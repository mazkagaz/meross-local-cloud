# Documentation de l’intégration

## Organisation

- `architecture/` — vue des composants, flux et invariants.
- `specs/` — comportements normatifs : backend profils, entités, réparations,
  contrats, sécurité.
- `design/` — décisions d’architecture (ADR) et bilan de conception D5.
- `testing/` — stratégie, validation manuelle et matrice de traçabilité.
- `operations/` — branches, versions, publication et retour arrière.

## Index

### Architecture

- [Vue d’ensemble](architecture/OVERVIEW.md)

### Spécifications

- [Backend profils](specs/BACKEND-PROFILE.md)
- [Entités et identité](specs/ENTITIES-IDENTITY.md)
- [Configuration et réparations](specs/CONFIG-REPAIRS.md)
- [Sécurité et diagnostics](specs/SECURITY-DIAGNOSTICS.md)
- [Contrats broker](specs/CONTRACTS.md)

### Conception

- [Décisions D5 et ADR](design/D5-DECISIONS.md)
- [ADR-0001 — Backend profils obligatoire](design/ADR-0001-profile-only.md)
- [ADR-0002 — Identité historique](design/ADR-0002-historical-identity.md)
- [ADR-0003 — Transport et disponibilité](design/ADR-0003-transport-availability.md)

### Tests

- [Stratégie de test](testing/STRATEGY.md)
- [Matrice de traçabilité](testing/TRACEABILITY.md)
- [Validation de la bêta 3.0](testing/D5-VALIDATION.md)

### Exploitation

- [Branches, versions et publication](operations/RELEASING.md)

### Traductions

- [Politique de traduction](TRANSLATIONS.md)
- [Glossaire français / anglais](TRANSLATION-GLOSSARY.md)

Les documents techniques restent en français pour l’instant ; les pages
d’entrée (`README`, `info`) sont publiées en anglais avec une version
française en `*.fr.md`.
