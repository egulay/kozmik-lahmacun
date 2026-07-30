#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ddl="${repository_root}/backend/src/main/resources/ddl.sql"
backend_launcher="${repository_root}/scripts/backend-dev.sh"
compose_file="${repository_root}/infrastructure/compose.yaml"

latest_migration="$(
  find "${repository_root}/backend/src/main/resources/db/migration" \
    -maxdepth 1 -type f -name 'V*__*.sql' -print \
    | sed -E 's#^.*/V([0-9]+)__.*#\1#' \
    | sort -n \
    | tail -1
)"
ddl_latest="$(
  sed -nE 's#.*V([0-9]+)__.*#\1#p' "${ddl}" | sort -n | tail -1
)"
launcher_baseline="$(
  sed -nE 's/^export SPRING_FLYWAY_BASELINE_VERSION="([0-9]+)"/\1/p' \
    "${backend_launcher}"
)"
compose_baseline="$(
  sed -nE 's/^[[:space:]]*SPRING_FLYWAY_BASELINE_VERSION: "([0-9]+)"/\1/p' \
    "${compose_file}"
)"

if [[ -z "${latest_migration}" || "${ddl_latest}" != "${latest_migration}" \
    || "${launcher_baseline}" != "${latest_migration}" \
    || "${compose_baseline}" != "${latest_migration}" ]]; then
  echo "Demo schema baseline mismatch." >&2
  echo "Latest migration: ${latest_migration:-missing}" >&2
  echo "ddl.sql latest: ${ddl_latest:-missing}" >&2
  echo "backend-dev baseline: ${launcher_baseline:-missing}" >&2
  echo "compose baseline: ${compose_baseline:-missing}" >&2
  exit 1
fi

echo "Demo schema baseline matches V${latest_migration}."
