# Spécification — configuration et réparations

## Configuration

- Découverte mDNS du broker, formulaire unique hôte/HTTPS 2004/MQTT 2001.
- HTTPS obligatoire ; CA récupérée depuis `/ca.crt`, vérifiée et épinglée.
- Login local ; réauthentification sur token invalide.
- Options : uniquement l’user-agent HTTP personnalisé. Un changement recharge
  l’intégration pour l’appliquer aux clients HTTP.

## Suivi des appareils

- Chaque `devList` réussi met à jour la liste connue.
- Une absence continue de 48 h crée une réparation de retrait.
- Le retour de l’appareil efface la réparation.
- Un échec HTTP ne compte pas comme absence.
- Un push `Appliance.Control.Unbind` supprime immédiatement l’appareil, ses
  subdevices, ses entités et son runtime.

## Appareil sans profil

- Aucune entité n’est créée.
- Une réparation non corrigeable `unsupported_device` expose nom, UUID et type.
- L’ajout du profil et le changement de révision du catalogue effacent la
  réparation.

## Diagnostics

- L’état de l’adapter expose : état, révision, nombre de profils, appareils
  associés/non associés, erreurs de compilation, compteurs runtime/scheduler,
  signature et empreinte de clé.

## Critères d’acceptation

- INT-CFG-001, INT-REPAIR-001.
- Tests : `test_config_flow.py`, `test_missing_devices.py`,
  `test_repairs.py`, `test_d5_hardening_functional.py`.
