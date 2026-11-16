# Meross Local Cloud — intégration Home Assistant pour broker local

![Meross Local Cloud](custom_components/meross_cloud/brand/logo.png)

Intégration **non officielle** pour Home Assistant, distribuée via HACS. Elle
pilote les appareils Meross appairés à un broker local, sans passer par le cloud
Meross pour l'usage quotidien. Elle ne propose que le mode local : aucun
identifiant du cloud officiel n'est demandé ni utilisé.

Ce fork ajoute le support MRS100 :

- entités `number` pour les durées d'ouverture/fermeture ;
- boutons **Start calibration** / **Stop calibration** ;
- capteur **Calibration status**.

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

## Avant de commencer

1. L'add-on **Meross Local Broker** est installé et démarré.
2. Un **compte local** a été créé dans l'add-on (login et mot de passe).
   N'utilisez pas votre compte Meross officiel : ce compte est indépendant.
3. Le MRS100 a été appairé avec **Meross Local Pairer**.
4. **HACS** est installé dans Home Assistant.
5. Home Assistant 2025.6 ou plus récent (testé avec 2026.11).

## Installation avec HACS

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
3. L'assistant lance directement la configuration du broker local et tente de
   le découvrir en mDNS. Renseigner les champs :

| Champ | Valeur |
|---|---|
| HTTP API Endpoint | `http://homeassistant.local:2003` |
| MQTT Address | `homeassistant.local:2001` |
| Local login | le compte local de l'add-on, par exemple `meross-local` |
| Password | le mot de passe local |
| Skip MQTT certificate validation | **coché** (certificat auto-signé) |

Le login local n'est pas obligatoirement une adresse email : un simple nom
d'utilisateur suffit. **N'utilisez jamais les identifiants du cloud Meross
officiel** ; l'intégration ne contacte que le broker local.

4. Valider. Les appareils déjà appairés apparaissent avec leurs entités.

Si Home Assistant n'est pas joignable via `homeassistant.local`, remplacer par
son adresse IP (`http://192.168.x.x:2003` et `192.168.x.x:2001`). Dans ce cas,
utiliser la configuration manuelle des identifiants dans Meross Local Pairer.

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
| Erreur de connexion HTTP | adresse `http://…:2003`, pas HTTPS |
| Erreur MQTT | adresse `…:2001`, `Skip MQTT certificate validation` coché |
| Entités absentes | redémarrer HA après l'appairage, puis recharger l'intégration |
| Statut de calibration bloqué | vérifier les logs de l'add-on et le capteur `Calibration status` |

## Origine, licence et historique

Fork non officiel de
[albertogeniola/meross-homeassistant](https://github.com/albertogeniola/meross-homeassistant),
créé par Alberto Geniola, sous **licence MIT**. Le copyright d'origine et la
notice de licence sont conservés dans `LICENSE`, avec une ligne pour les
modifications du fork. Voir aussi `NOTICE`, `MODIFICATIONS.md` et `LEGAL.md`.

Ce fork n'est ni affilié, ni approuvé, ni sponsorisé par Meross ou l'auteur
upstream. Meross est une marque de son propriétaire respectif.
