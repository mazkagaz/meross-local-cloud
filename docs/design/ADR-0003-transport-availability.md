# ADR-0003 — Transport et disponibilité

## Statut

Accepté — D5-b/D5-e.

## Contexte

Le manager fournissait autrefois le transport, la découverte et l’état en
ligne. Sa suppression impose de rendre ces responsabilités explicites.

## Décision

- Une seule connexion MQTT applicative est créée par l’adapter.
- Le coordinator authentifie et liste les appareils via `BrokerHttpClient`.
- La disponibilité combine `devList`, pushes `System.Online`/`Hub.Online` et
  l’état du transport.
- Un nouvel appareil détecté par polling déclenche un reload de l’entrée.
- Une reconnexion MQTT déclenche une rafale bornée de `devList` (0/5/15/30 s),
  l’invalidation du cache P3 et un rafraîchissement des schedulers ; elle est
  annulée au stop et ne se superpose pas à une rafale en cours.
- Un Unbind supprime appareil, subdevices, entités et runtime.
- Les commandes de sécurité (`cover.stop`) sont publiées immédiatement, sans
  attente d’ACK ni fenêtre de rate-limit MQTT ; l’ACK éventuel est traité comme
  un push non sollicité.

## Conséquences

- Les entités deviennent indisponibles sans reload lors d’une déconnexion.
- Le reload est le mécanisme de découverte d’un appareil nouvellement appairé.
- Le scheduler et le runtime restent les seuls propriétaires de l’état appareil.
