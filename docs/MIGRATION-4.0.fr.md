[English](MIGRATION-4.0.md) · **Français**

# Migration vers la 4.0.0 — changement de domaine Home Assistant

La version 4.0.0 change le domaine Home Assistant de l’intégration de
`meross_cloud` à `meross_local_cloud`. C’est une **rupture** pour les
installations existantes : l’ancienne config entry, les appareils et les
entités ne sont pas migrés automatiquement.

Le broker et le pairer sont inchangés. Seule l’intégration doit être supprimée
puis rajoutée.

## Ce qui change

- Le dossier du composant devient `custom_components/meross_local_cloud`.
- La config entry appartient au nouveau domaine. L’ancienne entrée
  `meross_cloud` devient orpheline et doit être supprimée.
- Les appareils et entités sont recréés. Les noms produisent en général le même
  `entity_id` si les anciennes entités sont supprimées avant ; vérifier les
  automatisations et tableaux de bord.
- Le cache d’état de l’intégration et l’état « appareil absent » ne sont pas
  repris. Ils se reconstruisent automatiquement au retour des appareils.
- L’adresse du broker, les ports et le compte local ne sont **pas** migrés :
  les ressaisir lors de l’ajout de la nouvelle intégration.

## Avant de commencer

1. Noter les `entity_id` importants et les automatisations/scripts/tableaux de
   bord qui les utilisent.
2. Faire une sauvegarde de Home Assistant.
3. Laisser le broker démarré ; aucune modification du broker n’est nécessaire.

## Étapes de migration

1. Dans Home Assistant, ouvrir **Paramètres → Appareils et services**.
2. Ouvrir l’ancienne entrée **Meross Local Cloud** et la supprimer. Ses
   appareils et entités sont retirés.
3. Dans **HACS → Intégrations → Meross Local Cloud**, désinstaller la version
   3.x, ou la mettre à jour vers 4.0.0.
4. Vérifier le dossier de configuration Home Assistant : si
   `custom_components/meross_cloud` existe encore, le supprimer. Seul
   `custom_components/meross_local_cloud` doit rester.
5. Redémarrer Home Assistant.
6. Rajouter l’intégration : **Paramètres → Appareils et services → Ajouter une
   intégration → Meross Local Cloud**.
7. Saisir l’adresse du broker, les ports HTTPS/MQTT et le compte local, comme
   lors de la première installation. La CA est récupérée et épinglée à nouveau.
8. Vérifier que les appareils et entités sont revenus. Ajuster les
   automatisations ou tableaux de bord si un `entity_id` a changé.

## Remarques HACS

HACS suit l’URL du dépôt, pas le domaine de l’intégration. La mise à jour 3.x →
4.0.0 fonctionne donc, mais l’ancien dossier peut rester sur le disque. Une
désinstallation/réinstallation propre, ou la suppression manuelle ci-dessus,
évite un dossier `custom_components/meross_cloud` résiduel.

## Retour arrière

Pour revenir à la 3.2.2, réinstaller cette version dans HACS, supprimer la
config entry 4.0.0, supprimer `custom_components/meross_local_cloud`,
redémarrer et rajouter l’intégration. Le retour arrière est aussi manuel.

## Dépannage

- **« Intégration introuvable » ou erreur au démarrage après mise à jour** :
  l’ancienne entrée `meross_cloud` est encore présente. La supprimer, puis
  ajouter la nouvelle entrée `meross_local_cloud`.
- **Entités dupliquées ou suffixes `_2`** : les anciennes entités n’ont pas été
  supprimées avant la création des nouvelles. Supprimer l’ancienne entrée,
  nettoyer les entités restantes, puis rajouter l’intégration.
- **Automatisations qui ne se déclenchent plus** : vérifier les `entity_id`
  utilisés. Les déclencheurs basés sur l’appareil peuvent nécessiter le nouvel
  appareil.
- **Statistiques/historique** : ils sont attachés à l’`entity_id`. Si le même
  identifiant est réutilisé, l’historique continue généralement ; sinon,
  réaffecter l’ancien statistic ID dans l’éditeur de statistiques.
