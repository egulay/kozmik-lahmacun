#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

require_command docker
require_command python3
require_env_file

compose config --quiet
python3 -m json.tool "${REPOSITORY_ROOT}/infrastructure/keycloak/kozmik-realm.json" >/dev/null

for script in "${REPOSITORY_ROOT}"/scripts/*.sh "${REPOSITORY_ROOT}"/infrastructure/*/*.sh; do
  bash -n "${script}"
done

if grep -R --line-number \
  --exclude='.env.example' \
  --exclude='deployment-secrets.env.example' \
  --exclude-dir='.git' \
  '^[A-Z_][A-Z_]*=CHANGE_ME$' "${REPOSITORY_ROOT}" >/dev/null; then
  echo "Found an unresolved secret placeholder outside .env.example" >&2
  exit 1
fi

echo "Static infrastructure verification passed."
