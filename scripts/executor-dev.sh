#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

require_command python3
require_command curl
require_env_file

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a
load_deployment_secrets

readonly executor_root="${REPOSITORY_ROOT}/executor"
readonly python_binary="${executor_root}/.venv/bin/python"
readonly dependency_stamp="${executor_root}/.venv/.kozmik-pyproject.toml"

if [[ ! -x "${python_binary}" ]]; then
  python3 -m venv "${executor_root}/.venv"
  "${python_binary}" -m pip install --upgrade pip
fi

if [[ ! -f "${dependency_stamp}" ]] \
  || ! cmp -s "${executor_root}/pyproject.toml" "${dependency_stamp}"; then
  "${python_binary}" -m pip install --editable "${executor_root}"
  cp "${executor_root}/pyproject.toml" "${dependency_stamp}"
fi

export PYSPARK_PYTHON="${python_binary}"
export PYSPARK_DRIVER_PYTHON="${python_binary}"
export JAVA_BASE_URL="http://localhost:${BACKEND_PORT:-8080}"
export VAULT_ADDR="http://localhost:${VAULT_PORT:-8200}"
export VAULT_TOKEN="${VAULT_EXECUTOR_TOKEN}"
export VAULT_EXECUTOR_SECRET_PATH="secret/data/kozmik-executor"
unset POSTGRES_PASSWORD REDIS_PASSWORD KEYCLOAK_ADMIN_PASSWORD
unset KEYCLOAK_BACKEND_CLIENT_SECRET INTERNAL_API_KEY KAFKA_MESSAGE_SIGNING_KEY
unset MINIO_ROOT_PASSWORD MINIO_EXECUTOR_PASSWORD MINIO_INGEST_PASSWORD
unset MINIO_ACCESS_KEY MINIO_SECRET_KEY OPENAI_COMPATIBLE_API_KEY OPENAI_API_KEY
unset VAULT_DEV_ROOT_TOKEN_ID VAULT_BACKEND_TOKEN VAULT_EXECUTOR_TOKEN
export KAFKA_BOOTSTRAP_SERVERS="localhost:${KAFKA_PORT:-9092}"
export MINIO_ENDPOINT="localhost:${MINIO_API_PORT:-9000}"
export EXECUTION_WORKER_ENABLED="true"
export INGESTION_WORKER_ENABLED="true"
export STREAM_INGESTION_WORKER_ENABLED="true"
export KAFKA_STREAM_INGESTION_TOPIC="ingestion.records.v1"
export KAFKA_STREAM_STATUS_TOPIC="ingestion.stream.status.v1"
export EXECUTION_EVENT_LEDGER_PATH="${executor_root}/.runtime/execution-events.sqlite3"
export INGESTION_EVENT_LEDGER_PATH="${executor_root}/.runtime/ingestion-events.sqlite3"
export STREAM_INGESTION_LEDGER_PATH="${executor_root}/.runtime/stream-ingestion.sqlite3"
if [[ "${PYTHON_LOG_DIR:-logs/python}" != /* ]]; then
  export PYTHON_LOG_DIR="${REPOSITORY_ROOT}/${PYTHON_LOG_DIR:-logs/python}"
fi

mkdir -p "${executor_root}/.runtime" "${PYTHON_LOG_DIR}"
cd "${executor_root}"

echo "Waiting for the Java control plane..."
until curl --fail --silent \
  "${JAVA_BASE_URL}/actuator/health/liveness" >/dev/null; do
  sleep 2
done

exec "${python_binary}" -m kozmik_executor.run
