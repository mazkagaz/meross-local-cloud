#!/usr/bin/env bash
# Fill GitHub/email placeholders in this integration repository.
# Usage: ./configure.sh <github-user> <email>
set -euo pipefail

if [ $# -lt 2 ]; then
  echo "usage: $0 <github-user> <email>" >&2
  exit 1
fi
USER="$1"
EMAIL="$2"
cd "$(dirname "$0")"

FILES=(
  README.md
  info.md
  hacs.json
  custom_components/meross_cloud/manifest.json
)

for f in "${FILES[@]}"; do
  [ -f "$f" ] || continue
  sed -i "s|<GITHUB_USER>|$USER|g; s|<YOUR_EMAIL>|$EMAIL|g" "$f"
done

echo "Configured:"
grep -n '<GITHUB_USER>\|github.com/' README.md hacs.json custom_components/meross_cloud/manifest.json | head
