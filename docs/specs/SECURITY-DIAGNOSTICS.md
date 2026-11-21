# Spécification — sécurité et diagnostics

## Transport et secrets

- HTTPS obligatoire vers le broker ; vérification de chaîne et du nom d’hôte
  selon le certificat épinglé.
- Le token et la clé MQTT ne sont jamais journalisés en clair.
- Les journaux pseudonymisent UUID, MAC, IP, emails et secrets.
- L’user-agent personnalisé ne doit pas contenir de secret.

## Diagnostics

Le téléchargement des diagnostics contient :

- version de l’intégration ;
- endpoint HTTP/MQTT et options non sensibles ;
- identifiants stockés expurgés (`token`, `key`, `password`, `issued_on`) ;
- CA, empreinte, validité, certificat serveur ;
- appareils issus de `devList` et état ONLINE/OFFLINE ;
- résumé du backend profils et compteurs.

## Règles

- Aucune donnée d’un appareil ou d’un profil ne doit être modifiable depuis les
  diagnostics.
- Les erreurs de catalogue ne doivent jamais exposer la clé privée de signature.
- Les réparations ne contiennent que nom, UUID et type d’appareil.

## Critères d’acceptation

- INT-SEC-001, INT-DIAG-001.
- Tests : `test_log_redaction.py`, `test_diagnostics.py`,
  `test_setup_tls.py`, `test_tls.py`.
