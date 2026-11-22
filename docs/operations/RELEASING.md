# Branches, versions et canal bêta

## Branches

- `main` : **livraisons publiques**. Aucun commit direct ; on y fusionne
  `dev` après validation.
- `dev` : intégration et tests. CI identique à `main`.
- La CI (`Tests`) tourne sur les deux branches et leurs pull requests.

## Versions

Le `manifest.json` doit **toujours** correspondre au tag publié :
le workflow de release refuse un tag dont la version diffère.

| Canal | Version | Tag | Release GitHub |
| ----- | ------- | --- | -------------- |
| stable | `4.0.0` | `v4.0.0` | normale |
| test | `3.0.0-beta.4` | `v3.0.0-beta.4` | **pre-release** |

## Publier une version de test

1. Sur `dev`, bumper `manifest.json` en `X.Y.Z-beta.N` (semver).
2. Commit, puis taguer et pousser :

```bash
git tag v3.0.0-beta.4
git push origin v3.0.0-beta.4
```

3. Le workflow `Release` vérifie manifest ↔ tag et crée une **pre-release**.
4. Dans HACS, activer **« Afficher les versions bêta »** pour voir et
   installer cette version. Sans cette option, les utilisateurs ne voient que
   les releases stables.

## Publier une version stable

1. Fusionner `dev` dans `main` après validation.
2. Bumper `manifest.json` en `X.Y.Z` stable (commit final).
3. Taguer et pousser depuis `main` :

```bash
git tag v3.0.0
git push origin v3.0.0
```

4. Le workflow valide la version et publie la release normale.

## Retour arrière

Dans HACS, réinstaller la dernière version stable, ou désactiver les bêtas.
Aucune release n’est supprimée.

## Broker (add-on)

Le magasin d’add-ons n’a pas de canal bêta équivalent à HACS : une version
présente dans le dépôt suivi est proposée aux utilisateurs. Les releases
stables du broker se font uniquement depuis `main` ; sa CI teste `main` et
`dev`.

L’intégration 3.1 exige un broker **1.2.2** ou plus récent (catalogue signé,
endpoints profils, routage ACK) ; **1.3.0** fournit le catalogue complet. Avant
de publier une version, vérifier que le broker installé expose bien ces
endpoints.
