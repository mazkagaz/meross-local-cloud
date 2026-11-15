# Meross Cloud IoT — broker local (fork MRS100)

Intégration Home Assistant non officielle pour piloter des appareils Meross
appairés à un **broker local**, sans cloud Meross au quotidien.

## Installation rapide

1. Installer d'abord l'add-on
   [Meross Local Broker](https://github.com/mazkagaz/meross-local-broker).
2. Appairer l'appareil avec
   [Local Pairer](https://github.com/mazkagaz/meross-local-pairer).
3. Dans HACS : **Intégrations → ⋮ → Dépôts personnalisés**, ajouter
   `https://github.com/mazkagaz/meross-cloud` en catégorie **Integration**.
4. Télécharger l'intégration, redémarrer Home Assistant.
5. **Paramètres → Appareils et services → Ajouter une intégration →
   Meross Cloud IoT**, choisir le mode
   **Connect to LAN-only broker**, puis saisir :
   - HTTP : `http://homeassistant.local:2003`
   - MQTT : `homeassistant.local:2001`
   - compte local de l'add-on
   - **Skip MQTT certificate validation** coché.

## Apports du fork MRS100

- entités `number` pour les durées d'ouverture et de fermeture ;
- boutons de démarrage/arrêt de calibration ;
- capteur de statut de calibration.

La procédure détaillée, les entités et le dépannage sont dans le
[README](https://github.com/mazkagaz/meross-cloud#readme).

## Licence

MIT. Fork non officiel de
[albertogeniola/meross-homeassistant](https://github.com/albertogeniola/meross-homeassistant) ;
attribution conservée dans `LICENSE`, `NOTICE` et `MODIFICATIONS.md`.
