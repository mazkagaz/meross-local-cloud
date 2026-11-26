## 4.0.6 — Température de couleur MSL610

- Support `ColorMode.COLOR_TEMP` pour les entités `light` dont le profil
  expose `color_temp`.
- Conversion native Meross 1–100 ↔ **2700–6500 K**.
- Commande `set_color_temp` vers `Appliance.Control.Light.temperature`.
- Tests golden frames MSL610 : luminosité, chaud/froid/mix, mise en veille,
  `ToggleX` et `TriggerX` non bloquant.
- Compatible broker **1.5.2** pour le profil bundled `meross.msl610` ;
  un override reste possible avec 1.5.1.
- La minuterie `TriggerX` n'est pas encore exposée comme entité.

## 4.0.5 — Correctif des profils et de la luminosité

Correctif de la mise à jour des profils et des réglages lumineux.

- Mise à jour d’un profil depuis l’entité `update` : les notifications
  persistantes sont désormais appelées comme des callbacks synchrones HA.
  L’erreur « a coroutine was expected, got None » est supprimée et le
  rechargement de l’intégration est lancé automatiquement.
- Limiteur MQTT local relevé à 10 messages/s avec une fenêtre de 20 messages :
  les réglages de luminosité/couleur ne déclenchent plus
  `MQTTRateLimitExceeded` lors de mouvements rapprochés du curseur.
- Tests ajoutés pour les notifications synchrones et le nouveau limiteur.
- Aucun changement broker ; compatible broker 1.5.1.

## 4.0.4 — Home Assistant Container

Version stable. Compatible broker **1.3.0+** ; **1.5.0** requis pour le mode
Docker autonome (HA Container).

- Formulaire manuel : ports HTTPS **2004** et MQTT **2001** préremplis, même
  sans découverte mDNS ; seul l’hôte et le compte local restent à saisir.
- Import de `BrokerProfileAdapter` déplacé au chargement du module : paho
  n’est plus importé sur la boucle d’événements, ce qui supprime
  l’avertissement « blocking call » de Home Assistant 2026.11.
- Manifeste : catégorie `hubs_protocols` déclarée ; suppression des logos
  redondants du dossier `brand/` (les icônes servent de repli).
- Documentation : section Home Assistant Container dans le README EN/FR et
  page de test Docker.
- Tests : 520 unitaires/intégration + 30 fonctionnels ; test E2E Docker
  HA Container + broker autonome.

## 4.0.3 — diagnostics expurgés

Version stable. Aucun changement fonctionnel hors confidentialité.

- Diagnostics : `user_email` et `user_id` sont désormais expurgés du bloc
  `stored_credentials` (`TO_REDACT`), comme `token`, `key` et `password`. Le
  test de diagnostics vérifie que ces deux champs sont masqués.
- README EN/FR : l’installation commence par la recherche dans HACS ; l’ajout
  en dépôt personnalisé reste documenté en repli.
- Correction demandée par la revue du listing HACS (PR #14768).

## 4.0.2 — images de marque régénérées

Version stable. Aucun changement fonctionnel.

- Images du dossier `brand/` régénérées depuis le master transparent
  1024×1024 : icônes 256×256 et 512×512, logos 256×256 et 512×512,
  variantes sombres identiques aux claires.
- Les installations existantes utilisent ces images localement ; dans le
  magasin HACS, l’icône réapparaît avec le listing par défaut (PR #14768).
  Les navigateurs cachent les images de marque pendant 7 jours.

## 4.0.1 — validation HACS et Hassfest

Version stable. Aucun changement fonctionnel.

- Manifeste : dépendances `network` et `zeroconf` déclarées, exigence
  `paho-mqtt>=2.1.0`, clés triées.
- Traductions : l’URL du broker passe par un placeholder dans le flux de
  configuration, plus d’URL brute dans `strings.json`/`translations`.
- `hacs.json` : suppression de la clé `domains`, refusée par le schéma HACS.
- Ajout des workflows **HACS Action** et **Hassfest**.

## 4.0.0 — nouveau domaine Home Assistant

Version majeure, rupture volontaire.

- Domaine Home Assistant `meross_cloud` → `meross_local_cloud` (dossier
  `custom_components/meross_local_cloud`, manifeste, loggers, identifiants de
  plateforme). L’ancienne config entry doit être supprimée puis l’intégration
  réajoutée : voir [docs/MIGRATION-4.0.fr.md](docs/MIGRATION-4.0.fr.md).
- La release inclut aussi la documentation bilingue préparée pour 3.2.3
  (README/info anglais + versions françaises), afin que HACS affiche la
  description anglaise.
- Aucun changement broker, pairer, profil ou API.

## 3.2.2 — présentation des entités number

Version stable. Broker **1.3.0+** ; **1.4.8 recommandé** pour la Position et
les durées en champ de saisie (profil MRS100 `2026.11.4`).

- Nouveau champ de profil `mode: slider|box` sur les entités `number` :
  l’intégration le mappe sur `NumberMode` (curseur ou champ typé avec flèches).
- Les anciennes intégrations ignorent ce champ et conservent le curseur.
- Moteur de profils **2.5.1**.
- Tests : 543, dont compilation/validation du mode et modes des durées/position.

## 3.2.1 — correctif de test fonctionnel

Version stable. Aucun changement de comportement par rapport à 3.2.0.

- `test_f3_1_open_close_stop` vérifie désormais la position du cover au lieu
  du dictionnaire complet, qui contient aussi la clé `movement`.
- Tests : 506 non fonctionnels + 30 fonctionnels.

## 3.2.0 — mises à jour manuelles et icônes de volet

Version stable. Broker **1.3.0+** ; **1.4.6 recommandé** pour les icônes MRS100
(profil `2026.11.3`). Pairer **2.0.9+** inchangé.

- Mises à jour de profils : `latest_version` est lu depuis le catalogue du
  broker, une notification persistante signale les nouvelles versions et
  l'entité `update` propose **Installer**. Le rechargement automatique de
  l'entrée à chaque changement de révision est supprimé : l'application reste
  manuelle.
- Rate limit MQTT local : 1 message/s soutenu et burst de 5 sur 5 s par
  appareil, au lieu de la limite cloud (200 messages/h, 5/90 s). Le `stop` du
  volet reste prioritaire.
- Moteur de profils **2.5** : source auxiliaire `movement` compilée sur une
  entité, sans entité Home Assistant supplémentaire.
- MRS100 : icône du cover pilotée par le mouvement (flèches haut/bas), puis
  volet ouvert, fermé ou partiel à l'arrêt (profil broker `2026.11.3`).
- Tests : 506 tests d'intégration (hors fonctionnels) et couverture moteur
  étendue au mouvement.

## 3.1.4 — bannière finale dans la documentation

Version stable. Aucun changement de comportement ; broker **1.3.0+** (1.3.1
recommandé) et pairer **2.0.9+** inchangés.

- Bannière finale appliquée dans le README et `info.md` (en-tête de document).
- Les logos et icônes restent issus du logo PNG transparent ; les variantes
  JPEG ne servent qu’aux emplacements qui exigent ce format.

## 3.1.3 — identité visuelle unifiée

Version stable. Aucun changement de comportement ; broker **1.3.0+** (1.3.1
recommandé) et pairer **2.0.9+** inchangés.

- Nouveau logo et nouvelle bannière communs aux trois briques.
- Logo transparent décliné pour les assets HA : logo, icône, variantes sombres
  et @2x.
- Pages README/info alignées sur le nouveau visuel.

## 3.1.2 — persistance générique de l’état

Version stable. Requiert le broker **1.3.0 ou plus récent** ; **1.3.1**
recommandé pour le correctif d’interrogation du volet.

- Les valeurs brutes du runtime de toutes les entités profils sont sauvegardées
  dans le Store Home Assistant et restaurées au démarrage, avant la création
  des entités.
- Restauration gardée par profil, clé d’entité et plateforme ; les valeurs non
  scalaires, inconnues ou issues d’un profil différent sont ignorées.
- La disponibilité reste pilotée par le transport/broker : une valeur restaurée
  ne rend jamais un appareil disponible.
- Sauvegarde différée à chaque mise à jour, immédiate au retrait d’un appareil
  et forcée à l’arrêt propre.
- Le cache P3 reste utilisé pour les données autoritatives du volet.

## 3.1.1 — maintien d’état du volet

Version stable. Requiert le broker **1.3.0 ou plus récent** ; **1.3.1** est
recommandé pour le correctif d’interrogation du volet.

- La position du volet et le statut de calibration sont amorcés depuis le cache
  P3 du broker lorsque le runtime est vide : ils survivent aux rechargements de
  l’intégration et aux redémarrages de Home Assistant.
- Le statut de calibration observé est réécrit dans le cache pour être restitué
  au démarrage suivant.
- Compatible avec le profil `meross.mrs100` 2026.11.2 (broker 1.3.1), qui ne
  sonde plus le namespace `Adjust` en lecture.

## 3.1.0 — catalogue D2b complet

Version stable. Requiert le broker **1.2.2 ou plus récent** (catalogue complet :
**1.3.0**) et le pairer **2.0.9 ou plus récent**.

- Moteur de profils 2.4 : entités `channel: $channels` clonées par canal
  découvert, sélection d’état par clé (`state.select`, liste ou objet),
  mapping booléen `on_values`, routage des sous-appareils par `id` ou `subId`
  et quirk `garage_door`.
- Catalogue enrichi : multiprises MSS425/MSP844, capteurs MS200/MS400/MS600,
  GS559, portes de garage MSG/RSG, purificateur MAP100, sprinkler MST100,
  compteurs EM/EM06, diffuseur MSXH0, HP110 et thermostat MTS9.
- Séparation MTS200/MTS300 et correction de l’échelle MTS300 (centièmes).
- Nouvelles trames dorées, tests fonctionnels par famille et matrice de
  traçabilité mise à jour.

## 3.0.0 — backend profils obligatoire

Version stable. Requiert le broker **1.2.2 ou plus récent** et le pairer
**2.0.9 ou plus récent**.

- Intégration entièrement pilotée par le catalogue de profils du broker ;
  suppression de `meross_iot`, du manager, des patches et des plateformes
  historiques.
- `paho-mqtt==2.1.0` comme seule dépendance runtime.
- Identités historiques conservées (`#BASE`, `#SUB`), migration des anciens
  IDs de bêta et conservation des entités/automatisations.
- Disponibilité par appareil, rafale de rechargement après reconnexion MQTT,
  détection des nouveaux appareils, arrêt de volet prioritaire.
- Réparations Unbind, appareil absent 48 h et appareil sans profil.
- Profils broker 1.2.x pour MRS100/MRS, thermostat, prises, hubs, lumières et
  diffuseur.
- API native du climat et tâches d’arrière-plan pour le catalogue.
- Documentation architecture/spécifications/ADR/traçabilité et validation 3.0.

## 3.0.0-beta.4 — démarrage et climat

Version de **test**. Requiert le broker **1.2.1**.

- La surveillance du catalogue et la rafale de reconnexion sont des tâches
  d’arrière-plan : le bootstrap Home Assistant ne les attend plus (#21).
- `ProfileClimate` utilise l’API native de température et ne fournit plus les
  propriétés dépréciées `current_temperature`/`target_temperature` (#20).
- Les températures courantes et cibles restent synchronisées à chaque écriture
  d’état, y compris sur les anciennes versions de Home Assistant.
- Le nom, le modèle et les versions d’un appareil recréé viennent désormais du
  broker (`devList`) au lieu du titre de l’entrée (`https://…:2004`).

## 3.0.0-beta.3 — resynchronisation après reconnexion

Version de **test**. Requiert le broker **1.2.1**.

- Après une reconnexion MQTT, rafale bornée de `devList` à 0/5/15/30 s pour
  retrouver rapidement les statuts online.
- Invalidation du cache volet P3 et rafraîchissement de tous les schedulers à
  chaque passe.
- Le premier connect au démarrage ne déclenche pas de rafale ; une seule
  rafale à la fois ; annulation au reload/stop.
- Un échec HTTP n’interrompt pas les tentatives suivantes.
- Documentation architecture/specs/traçabilité mise à jour.
- Corrections des textes utilisateur : versions broker 1.2.1, comportement réel
  de la calibration, Unbind, versions Home Assistant et cohérence des libellés.

## 3.0.0-beta.2 — stop volet immédiat

Version de **test**. Requiert le broker **1.2.1** pour les profils MRS100
corrigés.

- `cover.stop` est publié immédiatement sur `Appliance.RollerShutter.Position`
  (`position=-1`), sans attente d’ACK et sans rate-limit MQTT.
- L’ACK tardif est traité comme un push non sollicité ; le scheduler rafraîchit
  ensuite le namespace.
- Profils MRS100/MRS de broker 1.2.1 : lecture des listes
  `position`/`state`/`config`/`adjust`, commandes Position/Config/Adjust
  corrigées, calibration start=1/stop=2.
- Documentation réorganisée (architecture, specs, ADR, matrices de tests).

## 3.0.0-beta.1 — backend profils obligatoire

Version de **test** (pré-release, branche `dev`). Pour l’installer, activer
« Afficher les versions bêta » dans HACS.

Changement structurant : l’intégration ne dépend plus de `meross_iot`. Toutes
les entités proviennent désormais du catalogue de profils du broker.

- Suppression de `MerossManager`, des patches MQTT, de la calibration legacy et
  des plateformes historiques.
- Dépendance unique : `paho-mqtt==2.1.0`.
- `unique_id` et identifiants d’appareil historiques conservés, y compris
  `#BASE:<uuid>` et `#BASE:<hub>#SUB:<id>` ; les identifiants de la bêta 2.5
  sont nettoyés au démarrage.
- Disponibilité par appareil pilotée par `devList`, les pushes `Online` et
  l’état de la connexion MQTT.
- Nouvel appareil détecté : rechargement automatique de l’intégration.
- Appareil sans profil : aucune entité et réparation explicite
  « Aucun profil pour … ». Ajouter le profil au catalogue suffit ensuite.
- Unbind : suppression immédiate de l’appareil, de ses subdevices et entités.
- Options réduites à l’user-agent HTTP personnalisé ; un changement recharge
  l’intégration.

**Prérequis** : broker **1.2.0** ou plus récent (catalogue signé et endpoints
profils). Le pairer reste compatible.

**Limites connues** : les fonctions absentes du catalogue (garage, DND,
température de couleur, certaines consommations/énergie, familles D2b non
portées) ne créent plus d’entités tant que leur profil n’est pas publié. Les
profils MRS100 actuels décrivent encore des chemins de payload à corriger ; le
tuning est prévu après validation de la bêta.

**Validation** : suivre
[docs/testing/D5-VALIDATION.md](docs/testing/D5-VALIDATION.md).
Retour arrière : réinstaller la version stable **2.4.6** dans HACS, puis
redémarrer Home Assistant.

## 2.5.0-beta.1 — validation D5

Version de **test** (pré-release, branche `dev`). Pour l’installer, activer
« Afficher les versions bêta » dans HACS.

- Backend profils : catalogue signé Ed25519, registre, matching, compilation,
  scheduler central, batching `Multiple`, dispatch runtime.
- Entités issues des profils (switch, light, sensor, binary_sensor, cover,
  number, button, climate, fan, humidifier, update) et option avancée
  `profile_entities_only` pour la bascule sans perte de `unique_id`.
- Accès HTTP broker signé sans `meross_iot` pour la config flow, la liste des
  appareils, le catalogue et le cache volet.
- Contrats API broker et tests fonctionnels H2 (simulateurs MRS100, MSS310,
  hub, MTS200, lumière, diffuseur, bus MQTT en mémoire).
- Le reste du parc (garage, purificateurs, sprinklers, multiprises) garde le
  repli historique.

**Prérequis de test** : un broker avec le support du catalogue de profils.
Le broker public 1.1.3 ne contient pas encore ces endpoints : installer la
build broker de développement avant d’activer `profile_backend`.

Retour arrière : réinstaller la version stable 2.4.6 dans HACS.

## 2.4.6

- Pont temporaire pour les volets : `cover` et `number` rétablissent
  `update_before_add=True`, car sans mise à jour initiale les entités
  restaient dans un état erroné et les commandes échouaient.
- Les autres plateformes conservent `update_before_add=False` (P1).
- Ce pont sera supprimé en D3 avec le scheduler central par appareil.

## 2.4.5

- Les entités de plateforme ne déclenchent plus de mise à jour complète de
  l'appareil lors de leur ajout (`update_before_add=False`). Le manager a déjà
  découvert et mis à jour les appareils avant le montage des plateformes.
  Corrige les mises à jour `Appliance.RollerShutter.Config` en double et les
  délais de démarrage de plus de 10 secondes.
- Les capteurs qui se rafraîchissent eux-mêmes (température, électricité, DND)
  conservent leur polling périodique.

## 2.4.4

- Corrige réellement les timeouts de la sonde profils : la résolution des
  réponses MQTT (transaction par `messageId`) vivait dans la couche HA de
  meross_lan, exclue de la vendorisation. Le client applicatif de l'adaptateur
  l'implémente désormais lui-même.
- Journalisation DEBUG instrumentée : connexion MQTT, trames reçues, requêtes
  de descripteurs ; côté broker, suivi `messageId → topic de réponse` et
  routage ACK.
- Obfuscation automatique des journaux de l'intégration : UUID, MAC, IP,
  emails, identifiants d'application et secrets (`sign`, `key`, `token`,
  `password`, `Basic`) remplacés par des pseudonymes stables.
- Suppression des avertissements de dépréciation HA : `device_registry`
  (`async_entries_for_config_entry`, `config_entry_id`) et
  `CONN_CLASS_CLOUD_PUSH`.
- Le capteur **Broker profile backend** est retiré du registre quand l'option
  est désactivée.

## 2.4.3

- Supprime le dernier accès fichier à l'import du socle vendorisé
  (`debug.secret.json` de MEROSSDEBUG), qui déclenchait encore le détecteur de
  blocage de Home Assistant.
- User-Agent personnalisé : le défaut `MerossHA/<version>` n'est plus figé dans
  les options et suit désormais la version du manifest ; une valeur
  `MerossHA/...` déjà enregistrée est traitée comme le défaut.

## 2.4.2

- Corrige l'échec de chargement du backend profils : `devices.json` du socle
  vendorisé était lu à l'import, ce que Home Assistant refuse sur la boucle
  événementielle (`blocking call`, puis `IndexError` dans son détecteur).
  Le catalogue est désormais chargé à la première utilisation.

## 2.4.1

- Sonde du backend profils non bloquante : elle démarre en tâche de fond après
  le montage des plateformes, avec un budget global de 20 s, 5 s par appareil
  et abandon au premier échec. Le capteur **Broker profile backend** est créé
  immédiatement (`starting`, puis `connected`/`error`).
- Corrige le rechargement très long et l'absence de capteur lorsque les ACK
  `System.All` timeoutaient.

## 2.4.0

- Opt-in device-profile backend (`profile_backend`, disabled by default):
  vendored merossclient v6.0.2 (restricted subset), app-style MQTT transport
  with the broker CA, profile-catalog fetch and per-device descriptors.
- Requires broker **1.1.0** for the read-only profile endpoints; failure of
  the probe never blocks normal setup.
- Diagnostic sensor **Broker profile backend** (state, revision, profile and
  device counts, last error) when the option is enabled.
- Messages and documentation now refer to broker 1.0.0 instead of alpha99.

## 2.3.2

- Devices left behind in the Home Assistant registries by earlier versions are
  now tracked even when the broker never reports them again: at setup, the
  integration reconciles the devices it owns against the HTTP discovery and
  feeds the existing 48 h repair.
- The repair also finds devices absent from the local manager through their
  `#BASE:<uuid>` registry identifier, so confirming it really removes them.

## 2.3.1

- Unbind: the device and its entities are now really deleted from the Home
  Assistant registries. Calling `entity.async_remove()` alone kept a disabled
  entity-registry entry and wrote an unavailable "restored" state, so the
  device stayed visible after a broker-side removal. The integration now
  removes the entity entry, the state, and the device entry.

## 2.3.0

- Device removals no longer leave ghost entities. When the broker announces an
  `Appliance.Control.Unbind` (broker alpha101 or later), the integration
  removes the corresponding entity as before and stops tracking the device.
  The broker sends this event within 60 seconds of the deletion (immediately
  when the agent reconnects), which is the normal delay before the entities
  disappear.
- A device that has not been reported by a successful HTTP poll for 48 hours
  raises a fixable repair issue. Confirming it deletes the device and its
  entities from Home Assistant; re-pairing with the same UUID recreates them.
  Failed polls never start or reset the countdown, and a returning device
  clears the issue automatically.

## 2.2.0

- Reject port 2003 in the HTTPS and MQTT port fields: it is reserved. The
  form returns the standard “Port 2003 is reserved.” error and blocks
  validation.

## 2.1.3

- Correct the exposed-ports note: the port mappings are configured in
  Settings → Apps → Meross Local Broker → Configuration, not in a Home
  Assistant Network tab.

## 2.1.2

- Add a note to the setup form, in both the detected and not-detected states:
  if the add-on's exposed ports were changed (Home Assistant Network tab),
  enter the address and ports manually.

## 2.1.1

- Remove HTML from the config flow description. Home Assistant formats these
  strings as ICU messages and rejects rich-text tags (`INVALID_TAG`). The
  detected-broker status is now bold; the missing-broker state keeps the
  native red error banner.

## 2.1.0

- Replace the simple/advanced flow with a single form: Meross Local Broker
  address (host only), HTTPS port and MQTT port, all prefilled from mDNS
  discovery, plus a single example line above the fields.
- A detected broker shows “Broker detected automatically” in green; an
  undetected broker shows “Broker not detected” in red with a link to the
  broker installation documentation.
- The Advanced settings checkbox and step are removed; the MFA field is shown
  only when the broker requires it.
- Add a French translation.

## 2.0.0

- **Breaking:** the broker must be reached over HTTPS with a valid CA (broker
  **alpha99 or later**). Plain HTTP (port 2003), the “Skip HTTP/MQTT
  certificate validation” options and the unverified fallback are removed.
- The CA is fetched from `/ca.crt`, validated and pinned; HTTP and MQTT always
  verify the chain, with hostname verification when the server certificate
  covers the configured host.
- Diagnostics include the server certificate (subject, issuer, validity, SANs)
  and the HTTP/MQTT verification state.
- Existing entries using an `http://` endpoint or relying on the skip options
  must be reconfigured with the `https://…:2004` endpoint after updating the
  broker.

## 1.5.3

- Evaluate the server certificate SANs even when the stored skip option is
  true, so hostname verification is enabled as soon as the broker CA is
  trusted. Previously the skip flag prevented the SAN lookup and left
  `ca_check_hostname` false.

## 1.5.2

- Add diagnostics support: the downloaded diagnostics include the integration
  and meross_iot versions, the entry settings, the broker CA state (validity,
  fingerprint, SAN hostnames, hostname verification) and the device list.
  Tokens, keys and passwords are redacted.

## 1.5.1

- Declare the integration logger in the manifest so the Home Assistant log
  page filtered on Meross Local Cloud shows its messages.
- Log an unconditional INFO line at setup with the integration version, the
  pinned CA fingerprint and whether hostname verification is enabled.

## 1.5.0

- Trust the broker CA for HTTP and MQTT. The CA is downloaded from `/ca.crt`,
  validated (`CA:TRUE`) and pinned by SHA-256 in the config entry; a change is
  logged and the new CA is trusted automatically.
- HTTP and MQTT TLS contexts are built from that CA, with hostname
  verification enabled when the server certificate covers the configured host
  (the broker now publishes LAN IP SANs).
- The silent fallback to disabled verification is removed. When a valid CA is
  available it is used even if the old skip option is stored; the skip option
  remains a fallback for brokers without a valid CA.

## 1.4.23

- Revert 1.4.22: turning on the panel light no longer modifies the DND mode.
  This restores the meross_lan-aligned behavior of 1.4.21, with the ACK
  handling fix from 1.4.20.

## 1.4.22 (reverted in 1.4.23)

- Turning on the MRS100 panel light now disables Do Not Disturb first (mode
  `DND_DISABLED`) and waits briefly before sending the light command. DND
  gates the panel LEDs, so the light command was ignored while it was enabled
  — matching the manual sequence of toggling both entities that occasionally
  worked.

## 1.4.21

- Move the MRS100 light/DND diagnostics back to DEBUG. They were raised to
  INFO only to bypass the logger configuration while troubleshooting.

## 1.4.20

- Accept command ACKs delivered on `/app/<userId>/subscribe`. The broker agent
  forwards every device publish there, including GETACK/SETACK replies;
  meross_iot only matched ACKs on the app-specific response topic, so those
  replies were ignored and commands timed out (System.All, DNDMode, light).

## 1.4.19

- Align the MRS100 light entity with meross_lan: a plain on/off sends
  `Appliance.Control.Light` with only `channel` and `onoff`; luminance and the
  luminance capacity are added only when an actual brightness is requested.
  The entity state still follows the light digest and the last command.

## 1.4.18

- Light and DND diagnostics are logged at INFO, so they appear without any
  logger configuration. The setup line carries the integration version.

## 1.4.17

- More debug diagnostics for the MRS100 light: the cover light SET payload,
  acknowledgment and error, plus the raw light status and DND mode reads and
  writes. No behavior change.

## 1.4.16

- Drive the light of roller shutters and garage openers (MRS100) through
  `Appliance.Control.Light` instead of ToggleX, like meross_lan does: the
  ToggleX payload reported by covers is not standard and its state follows
  the motor activity. Turn-on sends `onoff=1` with a non-zero luminance and
  the luminance capacity; turn-off sends `onoff=0`. The light state prefers
  the light digest and falls back to the last command.

## 1.4.15

- Add debug diagnostics for MRS100 lights: the device abilities, whether it is
  ToggleX-controlled, the light state and the brightness on each turn on/off.
  No behavior change.

## 1.4.14

- Fix turning the MRS100 backlight back on. The light wrapper skipped the
  command when it believed the light was already on (some devices keep
  reporting `onoff=1`), and meross_iot then sent nothing. The turn-on command
  is now always sent; for non-toggle devices an explicit luminance is added
  so the `Appliance.Control.Light` payload is actually emitted.

## 1.4.13

- Light entities now expose Home Assistant-valid color modes: a
  brightness-only device uses `ColorMode.BRIGHTNESS` instead of `WHITE`
  (which the entity registry rejects), and the active mode always belongs to
  the supported set.
- Startup and reconnect log noise removed: `CommandTimeoutError` during
  device, power or DND updates is logged at debug level instead of a full
  traceback, and the last known state is kept.

## 1.4.12

- Build the MQTT TLS context in an executor and hand it to paho through
  `tls_set_context`. This removes Home Assistant's
  `Detected blocking call to load_verify_locations` warning emitted on every
  setup; verification and skip-validation modes are unchanged.

## 1.4.11

- Fix login against the broker HTTPS listener. `meross_iot` posts to
  `/v1/log/user` using the domain returned by the broker; the broker derives
  that domain from its nginx backend scheme and reports `http://…:2004`,
  which nginx rejects with HTTP 400. The login test now uses `async_login`
  and forces the configured endpoint, and stored credentials are migrated to
  it at setup.
- The simple form explains that **Advanced settings** must be checked and
  submitted to edit the endpoint, ports or TLS options.

## 1.4.10

- When no broker is discovered, the setup flow now opens the explicit
  endpoint/TLS form directly instead of showing a mode switch whose effect
  was invisible. The explicit form is also used when mDNS announces a service
  that cannot be resolved.
- When no mDNS service is found at all, probe the Home Assistant host's local
  IPv4 addresses on the default API ports (HTTPS 2004, then HTTP 2003).
- Restore the simple **Advanced settings** checkbox on the detected-broker
  form.

## 1.4.9

- When an mDNS service is announced but resolves without SRV/TXT/A records,
  the integration now probes the Home Assistant host's local IPv4 addresses
  on the API ports instead of giving up. This covers the add-on topology where
  the broker runs on the same host.
- When the TXT `https_port` record is missing (incomplete resolution), probe
  the broker default HTTPS port 2004 instead of assuming HTTPS is disabled.
- Extend the mDNS resolution timeout and log the probed candidates.

## 1.4.8

- Replace the **Advanced settings** checkbox with an explicit **Setup mode**
  selector: `Simple setup` or `Advanced settings (<version>)`. The option
  label comes from the integration code, not translations, so the running
  version is visible directly in the form. Select the advanced option and
  validate to open the explicit endpoint/TLS fields, even with empty values.
- Field label renamed to **Setup mode** in English, Spanish and Italian.

## 1.4.7

- The setup form now shows the running integration version and the detected
  broker, making it possible to confirm which code Home Assistant loaded
  without reading logs.
- Setup start, discovery results and the switch to advanced settings are
  logged at INFO.

## 1.4.6

- Discovery also probes the mDNS A/AAAA addresses, so a broker that does not
  publish the TXT `host` entry can still be found. IPv6 literals are formatted
  correctly in the derived URLs.
- The simple form no longer blocks submission when the broker address or the
  credentials are empty, so **Advanced settings** can be ticked and validated
  to reach the explicit fields. Missing values now return dedicated
  `missing_broker_host` / `missing_credentials` errors.
- The broker address accepts a pasted URL and keeps only its host.
- README: direct **Add to HACS** link.

## 1.4.5

- Automatic broker discovery now reads the add-on's mDNS TXT records
  (`host`, `http_port`, `https_port`) and probes HTTPS before HTTP, so the
  integration no longer assumes `homeassistant.local`.
- New simple setup: when a broker is discovered, only the local login and
  password are requested. Otherwise the Home Assistant host or IP and an
  HTTPS toggle are requested.
- Explicit endpoints, MQTT address and TLS options remain available under
  **Advanced settings**.
- A pasted address such as `http://10.0.0.5:2003/ca.crt` is reduced to its
  host before the endpoint is built.
- Reauthentication uses the same simple form and keeps the stored endpoints
  and TLS options.
- Spanish and Italian translations updated for the new flow.

## 1.4.4

- Climate entities use `native_temperature_unit`, `native_current_temperature`
  and `native_target_temperature`, removing Home Assistant's deprecation
  warnings.

## 1.4.3

- Replace the CA-chain verification introduced in 1.4.2: the CA generated by
  current brokers is not a valid CA (`basicConstraints` missing), so chain
  verification failed. When MQTT verification is enabled but the broker
  certificate cannot be verified, the integration now retries with validation
  disabled for the local broker and logs an explicit warning. Check
  "Skip MQTT certificate validation" to make that choice permanent.
- Keep the explicit CA bundle passed to paho, which avoids Home Assistant's
  blocking `load_default_certs` warning.
- Startup summary remains at INFO with the upstream project link.

## 1.4.2

- Verify the broker certificate chain with the CA served at `/ca.crt` for
  both HTTP and MQTT. Hostname matching is skipped because the local
  certificate may not contain the LAN IP. Existing entries fetch the CA during
  setup.
- Fall back to the configured skip options when the CA cannot be retrieved.
- Avoid Home Assistant's blocking `load_default_certs` warning by passing an
  explicit CA bundle to paho.
- Log the startup summary at INFO instead of WARNING and link the upstream
  project.
- Consume the broker's integer `bindTime`, removing the `meross_iot` warning
  for every device.

## 1.4.1

- Reauthentication now reuses the existing broker configuration: HTTP API
  endpoint, MQTT address and TLS options are prefilled, and the existing entry
  is updated in place instead of creating a duplicate when the endpoint changes.
- The reauthentication flow no longer resets the endpoint to
  `homeassistant.local:2003`.

## 1.4.0

- Support the broker HTTPS listener (`https://…:2004`, broker `alpha71`).
  The login step and every later HTTP call now accept the broker's
  self-signed certificate.
- New login option **Skip HTTP certificate validation**, opt-in and disabled
  by default. Check it only for the local broker's self-signed certificate;
  MQTT/TLS on port 2001 keeps its own skip option.
- The SSL error message now explains the option instead of suggesting plain
  HTTP only. Port 2003 remains available in plain HTTP.

## 1.3.22

- Fix every MRS100 entity update failing with `AttributeError: 'list' object
  has no attribute 'get'`. The pinned `meross_iot` release calls `.get()` on
  the default `light` digest even when the device has no light payload; a
  runtime patch now skips that mixin for non-light devices.
- Entity updates can no longer prevent an entity from being added when the
  third-party device update raises.

## 1.3.21

- Fix the 500 error when opening the integration options (gear icon):
  `OptionsFlow.config_entry` is now a read-only property in modern Home
  Assistant, so the flow must not assign it in its constructor.

## 1.3.20

- Keep entities available when the broker's HTTP device list reports a stale
  `offline`/`unknown` status (for example after a broker restart or when a
  second device is paired). The live MQTT state is now authoritative, and a
  failed HTTP poll no longer hides entities that MQTT still serves.

## 1.3.19

- Keep cover entities available when the HTTP device list transiently omits a
  device from a multi-device account: fall back to the MQTT online status
  instead of raising or marking the entity unavailable.

## 1.3.18

- Regenerate every icon from the transparent logo artwork (the JPEG source
  contained a checkerboard background).
- Set cover features through `_attr_supported_features` so open/close controls
  are exposed consistently, and log cover entity creation for diagnostics.

## 1.3.17

- Create cover entities even when the device reports no channel list, and
  apply the same guard to every platform. This restores the open/close cover
  controls for devices such as the MRS100.
- Ship dark and 2x brand image variants so the old Meross logo is no longer
  used in dark mode or on high-DPI screens.

## 1.3.16

- Fix the 500 error when opening the initial configuration flow: mDNS
  discovery is best-effort and any discovery-stack failure now falls back to
  the manual broker form instead of aborting the flow.

## 1.3.15

- Fix remaining naming inconsistencies in logs and notices (**Meross Local
  Cloud**, **Meross Local Broker**).

## 1.3.14

- Rename the integration to **Meross Local Cloud** and make it local-only: the
  broker-selection step is gone and the config flow goes straight to the local
  broker. The official Meross cloud is no longer offered.
- Config labels now ask for the **local login** (a username is enough, no email
  required) and warn against using Meross cloud credentials.
- Fix compatibility with Home Assistant 2026.11: use `ATTR_COLOR_TEMP_KELVIN`
  and `color_temp_kelvin` instead of the removed mired-based color temperature
  API.
- Refresh the README/info and add the project banner and brand icon.

## 1.3.13

- Add roller-shutter calibration buttons using `Appliance.RollerShutter.Adjust`:
  start auto-calibration (`value=1`) and abort/stop (`value=0`). The command
  uses a raw namespace string because `meross_iot` 0.4.9.2 has no
  `ROLLER_SHUTTER_ADJUST` enum member.
- Add a **Calibration status** diagnostic sensor. After a start it polls `GET
  Appliance.RollerShutter.Adjust` every 15 s for 2 min, following a 90 s
  delay (the app's first poll); otherwise it polls every 5 min. It reports
  `success`, `timeout`, `motor_blocked` or `failed_N`. Incoming Adjust pushes
  are not visible through `meross_iot` 0.4.9.2, hence polling.
- Add Home Assistant runtime tests (`tests/`, 12 cases) covering entity
  creation, command payloads, status mapping and monitoring.

## 1.3.12

- Add roller-shutter open/close duration number entities (`signalOpen`/`signalClose`) for MRS100-class covers.
- These entities work with the local broker add-on's persisted/replayed timing config.

## 1.3.11

- Fork for MRS100 / local Meross broker use.
- Roller-shutter cover support through the local broker abilities and the existing `RollerShutterTimerMixin`.
- Distribution via HACS custom repository.

# 1.3.10beta1 (2025-09-29)
- Update low-level dependency to 0.4.9.2, so to address #569
- Attempt to address #479

# 1.3.9 (2025-08-22)
- Address #563: let HA re-authenticate in case of expired token or password change

# 1.3.8 (2025-08-22)
- Address #552, #568 and similar.

# 1.3.7 (2025-06-18)
- Merge #555 to fix config_entries.async_forward_entry_setup deprecation (thanks @Easen!)

# 1.3.6 (2025-03-17)
- Updated meross_iot dependency to 0.4.9.0 which fixes issues with paho-mqtt
- Set Min HA version to 2025.3

# 1.3.5 & 1.3.4 - RETIRED

# 1.3.2beta1 (2024-05-04)
- Using MerossIot v0.4.7.2b3 which should add support for HomeKit Hubs (addressing #435 and possibly #400)
- Add support for BatteryLevel sensors for Meross SubDevices
- Address #499

# 1.3.1 (2024-04-28)
- Fix light platform deprecations
- Fix climate platform deprecations
- Add OPENING and CLOSING transient states for garage openers (#493)
- Change log verbosity from INFO to DEBUG (addresses #481)

# 1.3.1beta1 (2024-04-25)
- Implement MFA support (addressing #467)
- Avoid storing username/password credentials (addressing #486)

<!--next-version-placeholder-->
# 1.3.0 (2024-04-25)
- Add support for Meross OilDiffuser
- Refactor Meross Humidifier
- Update low level library to version 0.4.7.0
- Addressing #484 

# 1.2.12 (2024-01-27)
- Merge PR #449, fixing #448. Credits to @mguilherme

# 1.2.11 (2024-01-27)
- Using the latest API Endpoints from Meross, version 0.4.6.0
- Fix logging errors
- Fix deprecated constants usage

# 1.2.10 (2023-10-15)
- Using the latest API Endpoints from Meross
- Supporting energy sensor for plugs (#460, thanks to @benoitm974)
- Fixes component unloading issue (thanks to @TheHolyRoger)
- Attention: this version is not compatible with local-only addon

# 1.2.9b0 (2023-09-18)
- Update low-level library to v0.4.6.0rc2 to support new API endpoints
- Merged PR #447

# 1.2.8 (2022-01-05)
- Update low-level library to v0.4.5.7, addressing issue #414

# 1.2.7 (2023-01-04)
- Update low-level library to v0.4.5.4 to solve issue #412

# 1.2.6 (2022-07-27)
- Add roller shutter (MSR100) support
- Add thermostat (MTS200) support
- Implement support for LAN-LOCAL HTTP transport mode
- Update dependency to low-level meross_iot library (0.4.5.0)

# 1.2.5rc5 (2022-06-24)
- Fix log error caused by wrong variable reference

# 1.2.5rc (2022-06-23)
- Set addon to run on internal network
- Set default values for IP:PORT when using local addon and no mDNS info is gathered.

# 1.2.5rc3 (2022-06-23)
- Set addon to run on host network to make mDNS work
- Improve setup & UI experience

# 1.2.5rc2 (2022-06-18)

- Fix import error preventing the component from loading via HA

# 1.2.5rc1 (2022-06-18) - RETIRED

- Removed zeroconf HA discovery support as it is now managed via setup config flow.
- This component is now working with the [Meross Local Addon](https://github.com/albertogeniola/ha-meross-local-broker) (still in alpha, though).

# 1.2.5rc0 (2022-06-12)

- Merges 1.2.4-rc1 features with the latest master release (v1.2.4)  

# 1.2.4 (2022-06-12)

- Merges pull request #365 that fixes MSS3XX consumption readings

## 1.2.4-rc1 (2022-06-06)

### Feature

- Updated low-level library to MerossIot v0.4.4.7

## 1.2.4-rc0 (2022-06-05)

### Feature

- Updated low-level library to MerossIot v0.4.4.6

## 1.2.3 (2022-06-03)

### Feature

- Updated low-level library to MerossIot v0.4.4.5

## 1.2.2 (2022-05-29)

### Feature

- Prepared component for integration with the Meross local-addon
- Updated HACS badge URL (thanks to @wrt54g)

## 1.2.1 (2022-01-30)

### Feature

- Upgraded low-level library dependency to 0.4.4.4
- Added MSG200 Support  
- Updated default polling intervals: sensor polling every 30s, API discovery every 120s
- Added option to set a custom user-agent for HTTP communication against Meross API


## 1.2.0rc2 (2022-01-18)

### Feature

- Upgraded low-level library dependency to 0.4.4.3
- Improved HACS documentation
- Added .devcontainer and .vscode tasks to support local-debugging
