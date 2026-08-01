#!/usr/bin/env bash
set -euo pipefail

readonly repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly target="${repository_root}/.env"
readonly example="${repository_root}/.env.example"

if ! command -v openssl >/dev/null 2>&1; then
  echo "Required command not found: openssl" >&2
  exit 1
fi

postgres_password="$(openssl rand -hex 24)"
redis_password="$(openssl rand -hex 24)"
minio_password="$(openssl rand -hex 24)"
minio_executor_password="$(openssl rand -hex 24)"
minio_ingest_password="$(openssl rand -hex 24)"
keycloak_password="$(openssl rand -hex 24)"
client_secret="$(openssl rand -hex 32)"
demo_user_password="Kz!$(openssl rand -hex 12)"
demo_reporter_password="${demo_user_password}"
demo_scientist_password="${demo_user_password}"
demo_admin_password="${demo_user_password}"
internal_api_key="$(openssl rand -hex 32)"
kafka_message_signing_key="$(openssl rand -hex 48)"
vault_root_token="$(openssl rand -hex 32)"
vault_backend_token="$(openssl rand -hex 32)"
vault_executor_token="$(openssl rand -hex 32)"

if [[ -f "${target}" ]]; then
  append_secret_if_missing() {
    local key="$1"
    local value="$2"
    if ! grep -q "^${key}=" "${target}"; then
      printf '%s=%s\n' "${key}" "${value}" >> "${target}"
    fi
  }

  append_secret_if_missing "DEMO_REPORTER_PASSWORD" "${demo_reporter_password}"
  append_secret_if_missing "DEMO_SCIENTIST_PASSWORD" "${demo_scientist_password}"
  append_secret_if_missing "DEMO_ADMIN_PASSWORD" "${demo_admin_password}"
  append_secret_if_missing "INTERNAL_API_KEY" "${internal_api_key}"
  append_secret_if_missing "KAFKA_MESSAGE_SIGNING_KEY" "${kafka_message_signing_key}"
  append_secret_if_missing "VAULT_PORT" "8200"
  append_secret_if_missing "VAULT_DEV_ROOT_TOKEN_ID" "${vault_root_token}"
  append_secret_if_missing "VAULT_BACKEND_TOKEN" "${vault_backend_token}"
  append_secret_if_missing "VAULT_EXECUTOR_TOKEN" "${vault_executor_token}"
  append_secret_if_missing "MINIO_EXECUTOR_USER" "kozmik-executor"
  append_secret_if_missing "MINIO_EXECUTOR_PASSWORD" "${minio_executor_password}"
  append_secret_if_missing "MINIO_INGEST_USER" "kozmik-ingest"
  append_secret_if_missing "MINIO_INGEST_PASSWORD" "${minio_ingest_password}"
  append_secret_if_missing "LLM_PROVIDER" "LM_STUDIO"
  append_secret_if_missing "LLM_BASE_URL" "http://localhost:1234/v1"
  append_secret_if_missing "LLM_MODEL" "qwen3-coder-30b-a3b-instruct"
  append_secret_if_missing "LLM_TIMEOUT_SECONDS" "60"
  append_secret_if_missing "LLM_MAX_RETRIES" "2"
  append_secret_if_missing "LLM_MAX_CONTEXT_MESSAGES" "20"
  append_secret_if_missing "LLM_MAX_CONTEXT_CHARACTERS" "12000"
  append_secret_if_missing "EXECUTION_TIMEOUT_SECONDS" "7200"
  append_secret_if_missing "PYTHON_PLANNING_TIMEOUT_SECONDS" "660"
  append_secret_if_missing "PYTHON_CLASSIFICATION_TIMEOUT_SECONDS" "240"
  append_secret_if_missing "PYTHON_CHAT_STREAM_TIMEOUT_SECONDS" "240"
  append_secret_if_missing "SPARK_DRIVER_MEMORY" "8g"
  append_secret_if_missing "SPARK_DRIVER_MAX_RESULT_SIZE" "512m"
  append_secret_if_missing "JAVA_LOG_DIR" "logs/java"
  append_secret_if_missing "PYTHON_LOG_DIR" "logs/python"
  append_secret_if_missing "LOG_LEVEL" "INFO"
  append_secret_if_missing "PYTHON_LOG_LEVEL" "INFO"
  append_secret_if_missing "LOG_MAX_HISTORY_DAYS" "90"
  append_secret_if_missing "LOG_TOTAL_SIZE_CAP" "2GB"
  append_secret_if_missing "MAILPIT_UI_PORT" "8025"
  append_secret_if_missing "MAILPIT_SMTP_PORT" "1025"
  append_secret_if_missing "SMTP_HOST" "mailpit"
  append_secret_if_missing "SMTP_PORT" "1025"
  append_secret_if_missing "SMTP_FROM" "no-reply@kozmik.local"
  append_secret_if_missing "SMTP_FROM_DISPLAY_NAME" "\"Kozmik Lahmacun\""
  append_secret_if_missing "SMTP_AUTH" "false"
  append_secret_if_missing "SMTP_STARTTLS" "false"
  append_secret_if_missing "SMTP_SSL" "false"
  append_secret_if_missing "SMTP_USERNAME" ""
  append_secret_if_missing "SMTP_PASSWORD" ""

  executor_user="$(sed -n 's/^MINIO_EXECUTOR_USER=//p' "${target}" | tail -1)"
  executor_password="$(sed -n 's/^MINIO_EXECUTOR_PASSWORD=//p' "${target}" | tail -1)"
  awk -v user="${executor_user}" -v password="${executor_password}" '
    /^OPENAI_COMPATIBLE_API_KEY=/ { next }
    /^DEMO_REPORTER_PASSWORD=/ { print "DEMO_REPORTER_PASSWORD=Demo1234!"; next }
    /^DEMO_SCIENTIST_PASSWORD=/ { print "DEMO_SCIENTIST_PASSWORD=Demo1234!"; next }
    /^DEMO_ADMIN_PASSWORD=/ { print "DEMO_ADMIN_PASSWORD=Demo1234!"; next }
    /^MINIO_ACCESS_KEY=/ { print "MINIO_ACCESS_KEY=" user; next }
    /^MINIO_SECRET_KEY=/ { print "MINIO_SECRET_KEY=" password; next }
    /^SMTP_FROM_DISPLAY_NAME=Kozmik Lahmacun$/ {
      print "SMTP_FROM_DISPLAY_NAME=\"Kozmik Lahmacun\""; next
    }
    { print }
  ' "${target}" > "${target}.tmp"
  mv "${target}.tmp" "${target}"
  chmod 600 "${target}"
  echo "Existing .env retained; missing settings were added and MinIO executor credentials synchronized."
  exit 0
fi

sed \
  -e "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=${postgres_password}/" \
  -e "s/^REDIS_PASSWORD=.*/REDIS_PASSWORD=${redis_password}/" \
  -e "s/^MINIO_ROOT_PASSWORD=.*/MINIO_ROOT_PASSWORD=${minio_password}/" \
  -e "s/^MINIO_EXECUTOR_PASSWORD=.*/MINIO_EXECUTOR_PASSWORD=${minio_executor_password}/" \
  -e "s/^MINIO_ACCESS_KEY=.*/MINIO_ACCESS_KEY=kozmik-executor/" \
  -e "s/^MINIO_SECRET_KEY=.*/MINIO_SECRET_KEY=${minio_executor_password}/" \
  -e "s/^MINIO_INGEST_PASSWORD=.*/MINIO_INGEST_PASSWORD=${minio_ingest_password}/" \
  -e "s/^KEYCLOAK_ADMIN_PASSWORD=.*/KEYCLOAK_ADMIN_PASSWORD=${keycloak_password}/" \
  -e "s/^KEYCLOAK_BACKEND_CLIENT_SECRET=.*/KEYCLOAK_BACKEND_CLIENT_SECRET=${client_secret}/" \
  -e "s/^DEMO_REPORTER_PASSWORD=.*/DEMO_REPORTER_PASSWORD=${demo_reporter_password}/" \
  -e "s/^DEMO_SCIENTIST_PASSWORD=.*/DEMO_SCIENTIST_PASSWORD=${demo_scientist_password}/" \
  -e "s/^DEMO_ADMIN_PASSWORD=.*/DEMO_ADMIN_PASSWORD=${demo_admin_password}/" \
  -e "s/^INTERNAL_API_KEY=.*/INTERNAL_API_KEY=${internal_api_key}/" \
  -e "s/^KAFKA_MESSAGE_SIGNING_KEY=.*/KAFKA_MESSAGE_SIGNING_KEY=${kafka_message_signing_key}/" \
  -e "s/^VAULT_DEV_ROOT_TOKEN_ID=.*/VAULT_DEV_ROOT_TOKEN_ID=${vault_root_token}/" \
  -e "s/^VAULT_BACKEND_TOKEN=.*/VAULT_BACKEND_TOKEN=${vault_backend_token}/" \
  -e "s/^VAULT_EXECUTOR_TOKEN=.*/VAULT_EXECUTOR_TOKEN=${vault_executor_token}/" \
  "${example}" > "${target}"
chmod 600 "${target}"
echo "Created ${target} with generated local-development credentials."
