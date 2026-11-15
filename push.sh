#!/usr/bin/env bash
# Initialize, tag and push this HACS integration repository.
# Usage: ./push.sh <github-user>   (default branch: main, release tag: v1.3.19)
set -euo pipefail

USER="${1:?usage: $0 <github-user>}"
EMAIL="${2:?usage: $0 <github-user> <user-email>}"
cd "$(dirname "$0")"

if grep -Rq '<GITHUB_USER>' README.md hacs.json custom_components/meross_cloud/manifest.json 2>/dev/null; then
  echo "Placeholders still present; run ./configure.sh <user> <email> first." >&2
  exit 1
fi

if [ ! -d .git ]; then
  git init -b main
  git config user.name ${USER}
  git config user.email ${EMAIL}
fi
git add .
git commit -m "Meross Local Cloud fork for HACS" || true
git remote remove origin 2>/dev/null || true
git remote add origin "github.com-meross-cloud:${USER}/meross-local-cloud.git"
git push -u origin main

if ! git rev-parse "v1.3.19" >/dev/null 2>&1; then
  git tag -a v1.3.19 -m "Meross Local Cloud 1.3.17"
fi
git push origin v1.3.19

if command -v gh >/dev/null 2>&1; then
  gh release create v1.3.19 --title "Meross Local Cloud v1.3.19" \
    --notes "HACS-installable local-only integration for the Meross Local Broker add-on." \
    || true
fi

cat <<EOF

Pushed. Next:
  1. Make sure https://github.com/${USER}/meross-local-cloud is public.
  2. HACS -> Integrations -> three-dot menu -> Custom repositories
     URL: https://github.com/${USER}/meross-local-cloud
     Category: Integration
  3. Install, restart Home Assistant, add the Meross Local Cloud integration.
EOF
