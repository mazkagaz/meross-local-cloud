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
- Un Unbind supprime appareil, subdevices, entités et runtime.

## Conséquences

- Les entités deviennent indisponibles sans reload lors d’une déconnexion.
- Le reload est le mécanisme de découverte d’un appareil nouvellement appairé.
- Le scheduler et le runtime restent les seuls propriétaires de l’état appareil.
