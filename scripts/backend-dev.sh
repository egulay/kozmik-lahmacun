#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

require_command mvn
require_env_file

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a
load_deployment_secrets

export VAULT_ADDR="http://localhost:${VAULT_PORT:-8200}"
export VAULT_TOKEN="${VAULT_BACKEND_TOKEN}"
export SPRING_CONFIG_IMPORT="vault://"
export SPRING_APPLICATION_NAME="kozmik-backend"
export SPRING_CLOUD_VAULT_KV_APPLICATION_NAME="kozmik-backend"
export SPRING_CLOUD_VAULT_KV_DEFAULT_CONTEXT="kozmik-backend"
unset POSTGRES_PASSWORD REDIS_PASSWORD KEYCLOAK_ADMIN_PASSWORD
unset KEYCLOAK_BACKEND_CLIENT_SECRET INTERNAL_API_KEY KAFKA_MESSAGE_SIGNING_KEY
unset MINIO_ROOT_PASSWORD MINIO_EXECUTOR_PASSWORD MINIO_INGEST_PASSWORD
unset OPENAI_COMPATIBLE_API_KEY OPENAI_API_KEY
unset VAULT_DEV_ROOT_TOKEN_ID VAULT_BACKEND_TOKEN VAULT_EXECUTOR_TOKEN
export KEYCLOAK_CLIENT_ID="kozmik-backend"
export KEYCLOAK_ISSUER_URI="http://localhost:${KEYCLOAK_PORT}/realms/kozmik"
export SESSION_COOKIE_SECURE="false"
export DATABASE_SCHEMA="kozmik_lahmacun"
export SPRING_FLYWAY_BASELINE_ON_MIGRATE="true"
# ddl.sql replays all migrations before this process starts. Baseline at
# the same version so Flyway owns only migrations added after the demo snapshot.
export SPRING_FLYWAY_BASELINE_VERSION="31"
if [[ "${JAVA_LOG_DIR:-logs/java}" != /* ]]; then
  export JAVA_LOG_DIR="${REPOSITORY_ROOT}/${JAVA_LOG_DIR:-logs/java}"
fi
mkdir -p "${JAVA_LOG_DIR}"

cd "${REPOSITORY_ROOT}/backend"
exec mvn -Dmaven.repo.local=.m2 \
  -Dspring-boot.run.jvmArguments="-Dspring.application.name=kozmik-backend -Dspring.cloud.vault.kv.application-name=kozmik-backend -Dspring.cloud.vault.kv.default-context=kozmik-backend" \
  spring-boot:run
