# Contrats API broker ↔ intégration

Version **1**. Ces schémas décrivent les objets `data` renvoyés par l’API
authentifiée du broker. Le broker les valide dans ses tests ; l’intégration en
possède une copie identique dans `tests/contracts/` et la compare au dépôt
broker dans la CI (contrôle de dérive).

| Fichier                      | Endpoint / objet                            |
| ---------------------------- | ------------------------------------------- |
| `signin.json`                | `POST /v1/Auth/signIn` → données de session |
| `devlist.json`               | `POST /v1/Device/devList` → liste           |
| `profiles_rev.json`          | `POST /v1/Device/profiles/rev`              |
| `profiles.json`              | `POST /v1/Device/profiles`                  |
| `pubkey.json`                | `POST /v1/Device/profiles/pubkey`           |
| `roller_shutter_config.json` | `POST /v1/Device/rollerShutterConfig`       |

Règles :

- évolution additive uniquement (champ optionnel, valeur d’énumération) ;
- tout changement incompatible incrémente la version du contrat et se fait
  dans une release coordonnée broker + intégration ;
- les fixtures `fixtures/*.json` sont des exemples valides utilisés par les
  deux dépôts ; elles doivent rester identiques (octet pour octet).
