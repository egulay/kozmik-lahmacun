#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

require_command npm
require_env_file

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a
unset POSTGRES_PASSWORD REDIS_PASSWORD KEYCLOAK_ADMIN_PASSWORD
unset KEYCLOAK_BACKEND_CLIENT_SECRET INTERNAL_API_KEY KAFKA_MESSAGE_SIGNING_KEY
unset MINIO_ROOT_PASSWORD MINIO_EXECUTOR_PASSWORD MINIO_INGEST_PASSWORD
unset MINIO_ACCESS_KEY MINIO_SECRET_KEY OPENAI_COMPATIBLE_API_KEY OPENAI_API_KEY
unset VAULT_DEV_ROOT_TOKEN_ID VAULT_BACKEND_TOKEN VAULT_EXECUTOR_TOKEN

cd "${REPOSITORY_ROOT}/frontend"
if [[ ! -d node_modules ]]; then
  npm ci
fi

export BACKEND_BASE_URL="http://localhost:${BACKEND_PORT:-8080}"
exec npm run dev -- --host 0.0.0.0 --port "${FRONTEND_PORT:-5173}" --strictPort
