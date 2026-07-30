#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

require_command docker
require_command curl
require_env_file

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

"${REPOSITORY_ROOT}/scripts/smoke-test.sh"

table_count="$(compose exec -T postgres psql \
  --username "${POSTGRES_USER}" \
  --dbname "${POSTGRES_DB}" \
  --tuples-only \
  --no-align \
  --command "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'kozmik_lahmacun'")"
if (( table_count < 19 )); then
  echo "Expected the complete kozmik_lahmacun schema; found ${table_count} tables." >&2
  exit 1
fi

public_table_count="$(compose exec -T postgres psql \
  --username "${POSTGRES_USER}" \
  --dbname "${POSTGRES_DB}" \
  --tuples-only \
  --no-align \
  --command "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")"
if (( public_table_count != 0 )); then
  echo "Application tables must not be created in public." >&2
  exit 1
fi

entity_count="$(compose exec -T postgres psql \
  --username "${POSTGRES_USER}" \
  --dbname "${POSTGRES_DB}" \
  --tuples-only \
  --no-align \
  --command "SELECT count(*) FROM kozmik_lahmacun.business_entity")"
case "${1:-}" in
  --require-empty-entities)
    if (( entity_count != 0 )); then
      echo "Expected an empty entity registry; found ${entity_count} entities." >&2
      exit 1
    fi
    ;;
  --require-demo-data)
    if (( entity_count != 2 )); then
      echo "Expected the Sales and Telecom CDR demo entities." >&2
      exit 1
    fi
    ;;
  "")
    ;;
  *)
    echo "Unknown smoke verification mode: $1" >&2
    exit 2
    ;;
esac

curl --fail --silent \
  "http://localhost:${BACKEND_PORT:-8080}/actuator/health/liveness" >/dev/null
curl --fail --silent \
  --header "X-Internal-API-Key: ${INTERNAL_API_KEY}" \
  "http://localhost:${EXECUTOR_PORT:-8000}/internal/v1/health" >/dev/null
curl --fail --silent "http://localhost:${FRONTEND_PORT:-5173}/" >/dev/null

echo "Full browser-demo smoke verification passed (${table_count} isolated application tables)."
