# Meross Local Cloud — intégration Home Assistant pour broker local

![Meross Local Cloud](custom_components/meross_cloud/brand/logo.png)

Intégration **non officielle** pour Home Assistant, distribuée via HACS. Elle
pilote les appareils Meross appairés à un broker local, sans passer par le cloud
Meross pour l'usage quotidien. Elle ne propose que le mode local : aucun
identifiant du cloud officiel n'est demandé ni utilisé.

Ce fork ajoute le support MRS100 :

- entités `number` pour les durées d'ouverture/fermeture ;
- boutons **Start calibration** / **Stop calibration** ;
- capteur **Calibration status** ;
- suppression fiable des appareils oubliés (Unbind) et réparation des appareils
  absents depuis 48 h.

**Version stable 2.3.2**, compatible avec le broker **1.0.0** et le pairer
**2.0.8**.

## Les trois briques du montage

| Brique | Rôle | Dépôt |
|---|---|---|
| **Meross Local Broker** | add-on : broker MQTT + API locale | [mazkagaz/meross-local-broker](https://github.com/mazkagaz/meross-local-broker) |
| **Meross Local Cloud** | cette intégration Home Assistant (HACS) | [mazkagaz/meross-local-cloud](https://github.com/mazkagaz/meross-local-cloud) |
| **Meross Local Pairer** | application Android d'appairage | [mazkagaz/meross-local-pairer](https://github.com/mazkagaz/meross-local-pairer) |

```
MRS100 ──MQTT/TLS──> add-on Meross Local Broker ──API/MQTT──> cette intégration
                            ^
                            │ appairage initial
                       Meross Local Pairer (Android)
```

## Compatibilité des versions

| Brique | Version minimale | Remarques |
|---|---|---|
| Meross Local Cloud | 2.3.2 | cette intégration |
| Meross Local Broker | 1.0.0 | CA valide, HTTPS, Unbind |
| Meross Local Pairer | 2.0.8 | HTTPS 2004 uniquement |
| Home Assistant | 2025.6 | testé avec 2026.11 |

## Canal de test (bêta)

Les versions stables sont publiées depuis `main`. Les versions de test sont
des **pre-releases** `X.Y.Z-beta.N` issues de la branche `dev` : pour les
voir et les installer dans HACS, activer **« Afficher les versions bêta »**.
Sans cette option, seules les versions stables sont proposées. Procédure
complète : [docs/RELEASING.md](docs/RELEASING.md).

## Avant de commencer

1. L'add-on **Meross Local Broker** est installé et démarré.
2. Un **compte local** a été créé dans l'add-on (login et mot de passe).
   N'utilisez pas votre compte Meross officiel : ce compte est indépendant.
3. Le MRS100 a été appairé avec **Meross Local Pairer**.
4. **HACS** est installé dans Home Assistant.
5. Home Assistant 2025.6 ou plus récent (testé avec 2026.11).

## Installation avec HACS

[![Ouvrir votre instance Home Assistant et ajouter ce dépôt à HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=mazkagaz&repository=meross-local-cloud&category=integration)

Cliquer sur le badge ci-dessus, ou :

1. Ouvrir **HACS → Intégrations**.
2. Menu **⋮ → Dépôts personnalisés**.
3. Ajouter :
   - URL : `https://github.com/mazkagaz/meross-local-cloud`
   - Catégorie : **Integration**
4. Ouvrir la fiche **Meross Local Cloud**, télécharger la dernière version.
5. Redémarrer Home Assistant.

HACS installe l'intégration, pas l'add-on. L'add-on se trouve dans la boutique
des modules complémentaires (lien ci-dessus).

## Ajouter l'intégration

1. **Paramètres → Appareils et services → Ajouter une intégration**.
2. Chercher **Meross Local Cloud**.
3. L'assistant découvre le broker en mDNS et affiche un formulaire unique :

| Champ | Valeur |
|---|---|
| Meross Local Broker address | hôte ou IP, sans `https://` (prérempli si détecté) |
| HTTPS port | `2004` (prérempli si détecté) |
| MQTT port | `2001` (prérempli si détecté) |
| Local login | le compte local de l'add-on |
| Password | le mot de passe local |

Au-dessus des champs, un exemple générique est affiché :
`Exemple : 192.168.1.10 — HTTPS 2004, MQTT 2001`.

- Broker détecté : les champs sont préremplis et la mention
  « Broker détecté automatiquement » est affichée en vert.
- Broker non détecté : les champs sont vides et le message « Broker non
  détecté » s'affiche en rouge, suivi du lien
  **Installer ou vérifier l'installation de l'add-on Meross Local Broker**
  vers `https://github.com/mazkagaz/meross-local-broker#readme`.

4. Valider. Les appareils déjà appairés apparaissent avec leurs entités.

Le broker doit être en **1.0.0 ou plus récent**. Sa CA locale est valide : elle
est téléchargée depuis `/ca.crt`, vérifiée et épinglée par l'intégration, puis
utilisée pour HTTP et MQTT (vérification du nom d'hôte incluse lorsque le
certificat couvre l'adresse configurée).

Le HTTP non chiffré (port 2003) et les options « ignorer la validation du
certificat » ont été **supprimés** : toute connexion passe par TLS avec une CA
valide. Un broker ancien (CA invalide) doit être mis à jour avant de configurer
l'intégration.

Le login local n'est pas obligatoirement une adresse email : un simple nom
d'utilisateur suffit. **N'utilisez jamais les identifiants du cloud Meross
officiel** ; l'intégration ne contacte que le broker local.

## Oubli d'un appareil

- Quand le broker publie `Appliance.Control.Unbind` (broker 1.0.0), l'appareil
  et ses entités sont supprimés de Home Assistant dans la minute.
- Un appareil absent de tous les polls HTTP réussis pendant **48 heures**
  déclenche une réparation « Appareil plus appairé ». La confirmer supprime
  l'appareil et ses entités ; un retour de l'appareil annule la réparation.
- Les entrées héritées d'anciennes versions sont réconciliées au démarrage et
  suivent le même délai de 48 h. Pour nettoyer immédiatement, supprimer
  l'appareil dans **Paramètres → Appareils**.

## Options de l'intégration

Dans **Paramètres → Appareils et services → Meross Local Cloud → Configurer** :

- **Device communication options** : MQTT seul, HTTP local puis MQTT, ou HTTP
  local pour les GET uniquement. Le broker local fonctionne en MQTT seul.
- **Custom HTTP User-Agent** : laisser vide sauf besoin particulier.

Les diagnostics (**Paramètres → Appareils et services → Meross Local Cloud →
Télécharger les diagnostics**) sont expurgés : identifiants masqués, CA,
certificat serveur et état de vérification inclus. Les journaux de
l'intégration pseudonymisent UUID, MAC, IP, emails et secrets, pour pouvoir
être collés dans une issue sans masquage manuel.

## Entités créées

| Entité | Usage |
|---|---|
| `cover.*` | ouvrir, fermer, position |
| `number.*open*` | durée d'ouverture (10 à 120 secondes) |
| `number.*close*` | durée de fermeture (10 à 120 secondes) |
| `button.*start_calibration*` | démarrer la calibration |
| `button.*stop_calibration*` | interrompre la calibration |
| `sensor.*calibration_status*` | `in_progress`, `success`, `timeout`, `motor_blocked`, `failed_N` |

## Utilisation

- **Durées** : modifier les entités `number`. L'add-on persiste les valeurs et
  les réapplique après une reconnexion du volet.
- **Calibration** : lancer **Start calibration**. Le capteur passe à
  `in_progress`, puis au résultat. Le statut est interrogé après 90 secondes,
  puis toutes les 15 secondes pendant deux minutes, et toutes les 5 minutes en
  veille.
- **Stop calibration** : interrompt le mouvement en cours.

## Mise à jour

HACS → Intégrations → Meross Local Cloud → **Mettre à jour**, puis redémarrer
Home Assistant. Une nouvelle release GitHub est publiée pour chaque version.

## Dépannage

| Problème | Vérifier |
|---|---|
| HACS ne trouve pas le dépôt | dépôt public, catégorie **Integration**, release publiée |
| Aucun appareil découvert | add-on démarré, appareil ONLINE, compte local correct |
| Erreur de connexion HTTP | adresse du broker et port HTTPS `2004` (TLS obligatoire) |
| Certificat HTTPS refusé | mettre à jour le broker en 1.0.0 (CA valide) |
| Erreur MQTT | adresse `…:2001` ; broker 1.0.0 requis |
| Entités absentes | redémarrer HA après l'appairage, puis recharger l'intégration |
| Entités fantômes après un oubli | Unbind en 60 s, réparation 48 h, ou suppression manuelle de l'appareil |
| Statut de calibration bloqué | vérifier les logs de l'add-on et le capteur `Calibration status` |

## Origine, licence et historique

Fork non officiel de
[albertogeniola/meross-homeassistant](https://github.com/albertogeniola/meross-homeassistant),
créé par Alberto Geniola, sous **licence MIT**. Le copyright d'origine et la
notice de licence sont conservés dans `LICENSE`, avec une ligne pour les
modifications du fork. Voir aussi `NOTICE`, `MODIFICATIONS.md` et `LEGAL.md`.

Ce fork n'est ni affilié, ni approuvé, ni sponsorisé par Meross ou l'auteur
upstream. Meross est une marque de son propriétaire respectif.
