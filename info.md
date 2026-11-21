# Meross Local Cloud — broker local (fork)

![Meross Local Cloud](branding/meross-local-cloud-banner.jpeg)

Intégration Home Assistant non officielle pour piloter des appareils Meross
appairés à un **broker local**, sans cloud Meross au quotidien. Seul le mode
local est proposé : aucun identifiant du cloud officiel n'est utilisé.

## Installation rapide

1. Installer d'abord l'add-on
   [Meross Local Broker](https://github.com/mazkagaz/meross-local-broker).
2. Appairer l'appareil avec
   [Meross Local Pairer](https://github.com/mazkagaz/meross-local-pairer).
3. Dans HACS : **Intégrations → ⋮ → Dépôts personnalisés**, ajouter
   `https://github.com/mazkagaz/meross-local-cloud` en catégorie **Integration**.
4. Télécharger l'intégration, redémarrer Home Assistant.
5. **Paramètres → Appareils et services → Ajouter une intégration →
   Meross Local Cloud**, puis saisir :
   - adresse du broker : hôte ou IP (préremplie si le broker est découvert) ;
   - HTTPS : `2004`, MQTT : `2001` ;
   - le **login local** de l'add-on (un nom d'utilisateur suffit, ce n'est pas
     obligatoirement un email).

N'utilisez pas les identifiants du cloud Meross officiel : l'intégration ne
contacte que le broker local. Le broker **1.2.1** et TLS sont obligatoires.

## Apports du fork

- backend entièrement piloté par les profils d'appareils du broker, sans
  `meross_iot` ;
- catalogue profils signé, scheduler central et disponibilité par appareil ;
- entités `number` pour les durées d'ouverture/fermeture, boutons de
  calibration et capteur de statut ;
- réparations pour les appareils absents, dissociés ou sans profil.

La procédure détaillée, les entités et le dépannage sont dans le
[README](https://github.com/mazkagaz/meross-local-cloud#readme).

## Licence

MIT. Fork non officiel de
[albertogeniola/meross-homeassistant](https://github.com/albertogeniola/meross-homeassistant) ;
attribution conservée dans `LICENSE`, `NOTICE` et `MODIFICATIONS.md`.
