# Meross Local Cloud — intégration Home Assistant pour broker local

![Meross Local Cloud](branding/meross-local-cloud-banner.jpeg)

Intégration **non officielle** pour Home Assistant, distribuée via HACS. Elle
pilote les appareils Meross appairés à un broker local, sans passer par le cloud
Meross pour l'usage quotidien. Elle ne propose que le mode local : aucun
identifiant du cloud officiel n'est demandé ni utilisé.

Depuis la 3.0, l'intégration est **pilotée par les profils d'appareils** du
broker. Elle ne dépend plus de `meross_iot` : un profil décrit les namespaces,
les chemins de payload, les entités et les commandes, et le broker publie le
catalogue signé. Ajouter une famille d'appareils ne demande donc plus de
release de l'intégration, seulement un profil côté broker.

Familles actuellement décrites : MRS100, MSS310, multiprises MSS425/MSP844,
MSH300 avec sous-appareils MS100/MS130/MTS100/MS200/MS400/GS559/MST,
MTS200/MTS300/MTS9, MS600, lumières MSL, prises MSS, variateur MSS5,
diffuseurs MOD/MSXH0, purificateur MAP100, compteurs EM/EM06, garages MSG/RSG
et HP110.

- pour le MRS100 : entités `number` pour les durées d'ouverture/fermeture,
  boutons **Start calibration** / **Stop calibration**, capteur
  **Calibration status**, et icône du cover pilotée par le mouvement
  (flèches pendant le déplacement, états ouvert/fermé/partiel à l'arrêt) ;
- suppression fiable des appareils oubliés (Unbind), réparation des appareils
  absents depuis 48 h et réparation « appareil sans profil ».

## Appareils et testeurs recherchés

Le **MRS100** est l'appareil de référence du montage. Les autres familles du
catalogue (multiprises, capteurs, GS559, garage, purificateur, MST, compteurs
d'énergie, MSXH0, HP110, MTS9, etc.) sont décrites à partir du protocole et de
traces, mais **ont besoin de testeurs sur matériel réel**. Ouvrez une
[issue](https://github.com/mazkagaz/meross-local-cloud/issues) en précisant le
modèle, le firmware et les fonctions qui marchent ou non : c'est ce qui permet
de valider chaque profil. Le MRS100 n'est pas un prérequis : toute famille du
catalogue peut être testée.

**Version stable 3.2.2**, compatible avec le broker **1.3.0** (1.4.6
recommandé pour les icônes MRS100, 1.4.8 pour Position et les durées en champ
de saisie) et le pairer **2.0.9**.

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
| Meross Local Cloud | 3.2.2 | cette intégration, moteur profils 2.5 |
| Meross Local Broker | 1.3.0 | catalogue complet ; 1.3.1 volet ; 1.4.6 icônes MRS100 ; 1.4.8 Position |
| Meross Local Pairer | 2.0.9 | HTTPS 2004 uniquement |
| Home Assistant | 2025.6 | testé avec 2026.2 |

## Canal de test (bêta)

Les versions stables sont publiées depuis `main`. Les versions de test sont
des **préversions** `X.Y.Z-beta.N` issues de la branche `dev` : pour les
voir et les installer dans HACS, activer **« Afficher les versions bêta »**.
Sans cette option, seules les versions stables sont proposées. Procédure
complète : [docs/operations/RELEASING.md](docs/operations/RELEASING.md).
La documentation technique est indexée dans [docs/README.md](docs/README.md).

## Avant de commencer

1. L'add-on **Meross Local Broker** est installé et démarré.
2. Un **compte local** a été créé dans l'add-on (login et mot de passe).
   N'utilisez pas votre compte Meross officiel : ce compte est indépendant.
3. Au moins un appareil Meross (MRS100 ou autre famille du catalogue) a
   été appairé avec **Meross Local Pairer**.
4. **HACS** est installé dans Home Assistant.
5. Home Assistant 2025.6 ou plus récent (testé avec 2026.2).

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

Le broker doit être en **1.2.2 ou plus récent** pour le routage ACK et le
catalogue de profils ; **1.3.0** est requis pour les nouvelles familles
(multiprises, capteurs, garage, purificateur, MST, EM, MSXH0, HP110, MTS9).
Sa CA locale est valide : elle est téléchargée depuis `/ca.crt`, vérifiée et
épinglée par l'intégration, puis
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

- Quand le broker publie `Appliance.Control.Unbind`, l'appareil, ses
  sous-appareils et ses entités sont supprimés de Home Assistant immédiatement.
- Un appareil absent de tous les polls HTTP réussis pendant **48 heures**
  déclenche une réparation « Appareil plus appairé ». La confirmer supprime
  l'appareil et ses entités ; un retour de l'appareil annule la réparation.
- Les entrées héritées d'anciennes versions sont réconciliées au démarrage et
  suivent le même délai de 48 h. Pour nettoyer immédiatement, supprimer
  l'appareil dans **Paramètres → Appareils**.

## Backend profils

Le broker publie un catalogue signé (Ed25519). Au démarrage et à chaque
changement de révision, l'intégration :

1. vérifie la signature et charge les profils ;
2. interroge chaque appareil (`System.All`/`Ability`) ;
3. associe l'appareil au profil le plus précis ;
4. crée les entités et démarre un scheduler par appareil.

Un appareil sans profil ne crée aucune entité et déclenche une réparation
**Aucun profil pour …**. Corriger ou ajouter le profil dans le catalogue du
broker suffit. Lorsque la révision change, l'intégration signale la mise à
jour : une notification persistante apparaît et l'entité `update` du profil
propose **Installer**. L'installation reste manuelle afin de choisir le
moment ; aucun rechargement automatique n'est effectué.
Pour préparer un profil, voir le workflow overrides/capture du dépôt broker.

Les commandes MQTT locales utilisent une limite adaptée au broker local
(1 message/s soutenu, burst de 5 sur 5 s par appareil) au lieu de la limite
cloud de 200 messages/heure.

## Options de l'intégration

Dans **Paramètres → Appareils et services → Meross Local Cloud → Configurer** :

- **Custom HTTP User-Agent** : laisser vide sauf besoin particulier. Un
  changement recharge l'intégration pour s'appliquer à tous les appels HTTP.

Les diagnostics (**Paramètres → Appareils et services → Meross Local Cloud →
Télécharger les diagnostics**) sont expurgés : identifiants masqués, CA,
certificat serveur, appareils, état du backend profils (révision, signature,
appareils associés/non associés, erreurs) et compteurs du scheduler. Les
journaux pseudonymisent UUID, MAC, IP, emails et secrets, pour pouvoir être
collés dans une issue sans masquage manuel.

## Entités créées

| Entité | Usage |
|---|---|
| `cover.*` | ouvrir, fermer, position |
| `number.*open*` | durée d'ouverture (10 à 120 secondes) |
| `number.*close*` | durée de fermeture (10 à 120 secondes) |
| `button.*start_calibration*` | démarrer la calibration |
| `button.*stop_calibration*` | interrompre la calibration |
| `sensor.*calibration_status*` | `success`, `timeout`, `motor_blocked`, `failed_N` |

## Utilisation

- **Durées** : modifier les entités `number`. L'add-on persiste les valeurs et
  les réapplique après une reconnexion du volet.
- **Calibration** : lancer **Start calibration**. Le scheduler rafraîchit
  `Adjust` après la commande ; le capteur affiche ensuite le statut renvoyé par
  l’appareil (`success`, `timeout`, `motor_blocked`, `failed_N`).
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
| Certificat HTTPS refusé | mettre à jour le broker en 1.3.0 (CA valide) |
| Erreur MQTT | adresse `…:2001` ; broker 1.3.0 requis |
| Entités absentes | vérifier la réparation « appareil sans profil » et le catalogue broker |
| Appareil sans profil | ajouter ou corriger le profil dans le catalogue ; notification puis **Installer** sur l'entité `update` |
| Entités fantômes après un oubli | Unbind (≤ 60 s), réparation 48 h, ou suppression manuelle de l'appareil |
| Statut de calibration bloqué | vérifier les logs de l'add-on et le capteur `Calibration status` |

## Outils de développement

Les profils et les trames dorées s'appuient sur
[meross_lan](https://github.com/krahabb/meross_lan) (**MIT**) : son client
`merossclient` vendorisé (v6.0.2, commit épinglé) fournit le protocole et les
descripteurs, et ses traces `emulator_traces/` servent de référence pour les
familles sans capture locale. meross_lan n'est pas une dépendance runtime ;
il est utilisé pour la conception, les tests et la validation des profils.
Voir `NOTICE`, `MODIFICATIONS.md` et `vendor/merossclient/UPSTREAM.md`.

## Origine, licence et historique

Fork non officiel de
[albertogeniola/meross-homeassistant](https://github.com/albertogeniola/meross-homeassistant),
créé par Alberto Geniola, sous **licence MIT**. Le copyright d'origine et la
notice de licence sont conservés dans `LICENSE`, avec une ligne pour les
modifications du fork. Voir aussi `NOTICE`, `MODIFICATIONS.md` et `LEGAL.md`.

Ce fork n'est ni affilié, ni approuvé, ni sponsorisé par Meross ou l'auteur
upstream. Meross est une marque de son propriétaire respectif.
