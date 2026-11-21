# Validation de la bêta 3.0.0

Cette checklist valide le backend profils obligatoire (D5) sur une installation
réelle. Elle se fait sur la branche `dev`, avec la pré-release
`3.0.0-beta.2`.

## Prérequis

- Sauvegarde complète Home Assistant (Paramètres → Système → Sauvegardes).
- Broker **1.2.1** installé et démarré.
- Les 6 appareils de production appairés et en ligne.
- HACS configuré pour afficher les versions bêta.
- Accès aux diagnostics de l'intégration et aux journaux Home Assistant.

Ne pas modifier le broker ni les profils pendant la première passe : on valide
d'abord l'état publié du catalogue.

## Installation

1. HACS → Intégrations → Meross Local Cloud → installer
   **3.0.0-beta.2**.
2. Redémarrer Home Assistant.
3. Paramètres → Appareils et services → Meross Local Cloud : vérifier que
   l'entrée existante est chargée sans reconfiguration.
4. Télécharger les diagnostics et vérifier :
   - `version.integration == 3.0.0-beta.2` ;
   - `profile_backend.state == connected` ;
   - `catalog_signature == valid` ;
   - `devices_matched` égal au nombre d'appareils attendus ;
   - `devices_unmatched == 0` ou réparations « Aucun profil » expliquées ;
   - `compile_errors` vide ;
   - `runtime_errors` sans erreur nouvelle ;
   - `scheduler_polls` et `scheduler_batches` augmentent.

## Matrice fonctionnelle

Pour chaque ligne : état correct, commande SET, mise à jour PUSH, puis
indisponibilité et retour.

| Famille | Vérifications minimales | OK |
|---|---|---|
| MRS100 (volets) | position, ouvrir/fermer/stop, durée open/close, boutons de calibration, statut | ☐ |
| MSS310 (prises) | switch on/off, puissance, tension, courant | ☐ |
| MSH300 + MS100/MS130 | hub en ligne, température/humidité, batterie si exposée, `via_device` correct | ☐ |
| MTS100 (vanne) | température ambiante, consigne, mode chauffage/off | ☐ |
| MTS200 | température ambiante, consigne, mode | ☐ |
| Lumières MSL | on/off, luminosité, RGB | ☐ |
| Diffuseur | spray on/off ou mode, lumière | ☐ |

Notes MRS100 : le catalogue actuel décrit encore des chemins de payload à
corriger. Si une valeur ou un statut ne remonte pas, le noter sans bloquer la
validation ; le tuning se fera par overrides après la bêta.

## Cas dégradés

| Scénario | Résultat attendu | OK |
|---|---|---|
| Appareil hors ligne | entités indisponibles, pas de traceback, retour automatique en ligne | ☐ |
| Redémarrage du broker | entités indisponibles puis disponibles, aucun doublon | ☐ |
| Redémarrage de Home Assistant | mêmes `entity_id`, mêmes états, aucun appareil recréé | ☐ |
| Reload de l'intégration | aucune entité dupliquée, IDs stables | ☐ |
| Appareil sans profil | aucune entité + réparation « Aucun profil pour … » | ☐ |
| Ajout du profil manquant | la réparation disparaît au reload automatique | ☐ |
| Catalogue indisponible | intégration en erreur/retry, pas d'entités fantômes | ☐ |
| Signature invalide | catalogue refusé, erreur visible dans les diagnostics | ☐ |
| Unbind d'un appareil | appareil, subdevices et entités supprimés immédiatement | ☐ |
| Changement de révision du catalogue | reload automatique, compteurs et IDs cohérents | ☐ |

## Contrôles de non-régression

- [ ] Une seule connexion MQTT côté intégration (pas de double abonnement).
- [ ] Les ACK `GETACK`/`SETACK` ne sont consommés qu'une fois.
- [ ] Le scheduler regroupe les GET et ne duplique pas les SET.
- [ ] Aucun import ni paquet `meross_iot` dans Home Assistant.
- [ ] `paho-mqtt==2.1.0` installé par l'intégration.
- [ ] Les automatisations utilisant les volets fonctionnent sans modification.

## Retour arrière

1. HACS → Meross Local Cloud → menu → **Reinstaller** la version stable
   **2.4.6**.
2. Redémarrer Home Assistant.
3. Vérifier que les entités et automatisations historiques fonctionnent.
4. Ne supprimer ni l'entrée de configuration ni les appareils du registre.

Conserver les diagnostics et les journaux de la bêta pour l'analyse.

## Validation finale

- [ ] Les 6 appareils sont pilotables et suivis.
- [ ] Aucun doublon d'entité ou d'appareil.
- [ ] Automatisations et tableaux de bord inchangés.
- [ ] Aucun cas dégradé bloquant.
- [ ] Décision : publier **3.0.0** stable ou corriger avant.
