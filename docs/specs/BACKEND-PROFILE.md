# Spécification — backend profils

## Objectif

Construire les appareils et leurs entités uniquement depuis le catalogue signé
du broker et les descriptors MQTT.

## Catalogue

- Endpoints : `/v1/Device/profiles/rev`, `/profiles`, `/profiles/pubkey`.
- La révision et le nombre de profils sont lus avant le catalogue.
- Si `signature` est présent, la clé publique est récupérée et la signature
  Ed25519 vérifiée. Une signature absente est signalée `absent` ; une signature
  invalide met l’adapter en erreur et interdit la création d’entités.
- La révision surveillée toutes les 60 s ; un changement recharge l’entrée.

## Découverte et matching

- `devList` fournit l’UUID, le type, le sous-type et l’état en ligne.
- Le descriptor MQTT fournit le type, le firmware, les abilities, la MAC, les
  subdevices et les canaux découverts.
- Les payloads de sous-appareils sont routés par `id` ou par `subId` (MST).
- Les entités `channel: $channels` sont clonées pour chaque canal exposé ; leur
  `state.select` choisit l’élément de liste (ou l’objet unique historique) dont
  la clé vaut le canal. Moteur 2.3, refusé dans les templates de sous-appareils.
- `on_values` transforme une valeur brute en booléen (codes d’état GS559) ;
  le quirk `garage_door` interprète `open` pour les couvertures. Moteur 2.4.
- Le matching applique : MAC + sous-type, sous-type, type/abilities exacts,
  préfixe le plus long, puis `*`.
- Une ambiguïté est comptée ; un appareil sans profil est signalé par une
  réparation et ne crée aucune entité.

## Persistance d’état

- Les valeurs brutes du runtime sont sauvegardées dans le Store HA
  (`meross_local_cloud.runtime_state`), de façon différée et à l’arrêt propre.
- Les champs de `state` et de `movement` sont persistés (moteur 2.6), notamment
  `onoff` pour les lumières dont l’état ON/OFF vient de `ToggleX`.
- Elles sont restaurées au démarrage avant la création des entités, pour les
  appareils et sous-appareils dont le profil et la plateforme correspondent
  encore ; les valeurs non scalaires ou inconnues sont ignorées.
- La disponibilité n’est jamais restaurée : elle reste pilotée par le transport
  et le broker. Le cache P3 reste utilisé pour les données autoritatives du
  volet.

## Commandes dépendantes de l’état

- Le jeton `$brightness` (moteur 2.6) injecte la luminosité brute 0–100 de
  l’entité `light` dans un payload de commande. Il est refusé sur les autres
  plateformes.
- Une commande `set_color_temp` qui utilise `$brightness` exige une luminosité
  connue dans l’état ou fournie dans l’appel Home Assistant. Sinon l’entité
  lève `HomeAssistantError` sans envoyer de `SET`.

## Runtime et scheduler

- Un `DeviceRuntime` par appareil, un `DeviceScheduler` par appareil.
- Le scheduler regroupe les GET dans `Appliance.Control.Multiple`, applique un
  rate-limit et un backoff en échec.
- Les pushes sont routés vers le runtime ; un ACK sollicité n’est jamais
  dispatché deux fois.
- Les commandes passent par le transport puis rafraîchissent le namespace.

## États dégradés

| Cas | Comportement |
|---|---|
| HTTP broker indisponible | `ConfigEntryNotReady`, retry |
| token invalide | `ConfigEntryAuthFailed` |
| catalogue indisponible | adapter en `error`, aucune entité |
| signature invalide | catalogue refusé |
| MQTT indisponible | adapter en `error` ou entités indisponibles |
| appareil hors ligne | entités indisponibles, retour automatique |
| nouveau device | reload automatique de l’entrée |
| reconnexion MQTT | rafale `devList` à 0/5/15/30 s, invalidation P3, refresh schedulers |

## Critères d’acceptation

- INT-CAT-001, INT-MATCH-001, INT-RUNTIME-001, INT-SCHED-001.
- Tests unitaires et fonctionnels correspondants dans
  [TRACEABILITY](../testing/TRACEABILITY.md).
