#!/bin/sh
set -eu

export VAULT_ADDR="${VAULT_ADDR:-http://vault:8200}"
export VAULT_TOKEN="${VAULT_DEV_ROOT_TOKEN_ID:?required}"

until vault status >/dev/null 2>&1; do
  sleep 1
done

if ! vault secrets list -format=json | grep -q '"secret/"'; then
  vault secrets enable -path=secret kv-v2 >/dev/null
fi

vault policy write kozmik-backend /opt/kozmik/backend-policy.hcl >/dev/null
vault policy write kozmik-executor /opt/kozmik/executor-policy.hcl >/dev/null

if ! vault token lookup "${VAULT_BACKEND_TOKEN:?required}" >/dev/null 2>&1; then
  vault token create -id="${VAULT_BACKEND_TOKEN}" -policy=kozmik-backend \
    -orphan -no-default-policy >/dev/null
fi
if ! vault token lookup "${VAULT_EXECUTOR_TOKEN:?required}" >/dev/null 2>&1; then
  vault token create -id="${VAULT_EXECUTOR_TOKEN}" -policy=kozmik-executor \
    -orphan -no-default-policy >/dev/null
fi

write_backend_secret() {
  secret_path="$1"
  database_url="$2"
  smtp_host="$3"
  smtp_port="$4"
  vault kv put "${secret_path}" \
  "spring.datasource.url=${database_url}" \
  "spring.datasource.username=${POSTGRES_USER:?required}" \
  "spring.datasource.password=${POSTGRES_PASSWORD:?required}" \
  "spring.data.redis.password=${REDIS_PASSWORD:?required}" \
  "spring.security.oauth2.client.registration.keycloak.client-secret=${KEYCLOAK_BACKEND_CLIENT_SECRET:?required}" \
  "spring.mail.host=${smtp_host}" \
  "spring.mail.port=${smtp_port}" \
  "spring.mail.username=${SMTP_USERNAME:-}" \
  "spring.mail.password=${SMTP_PASSWORD:-}" \
  "spring.mail.properties.mail.smtp.auth=${SMTP_AUTH:?required}" \
  "spring.mail.properties.mail.smtp.starttls.enable=${SMTP_STARTTLS:?required}" \
  "spring.mail.properties.mail.smtp.ssl.enable=${SMTP_SSL:?required}" \
  "kozmik.mail.from=${SMTP_FROM:?required}" \
  "kozmik.mail.from-display-name=${SMTP_FROM_DISPLAY_NAME:?required}" \
  "kozmik.security.internal-api-key=${INTERNAL_API_KEY:?required}" \
  "kozmik.security.kafka-message-signing-key=${KAFKA_MESSAGE_SIGNING_KEY:?required}" >/dev/null
}

backend_smtp_host="${SMTP_HOST}"
backend_smtp_port="${SMTP_PORT}"
if [ "${SMTP_HOST}" = "mailpit" ]; then
  backend_smtp_host="localhost"
  backend_smtp_port="${MAILPIT_SMTP_PORT:-1025}"
fi

write_backend_secret secret/kozmik-backend \
  "jdbc:postgresql://localhost:${POSTGRES_PORT:-5432}/${POSTGRES_DB:?required}" \
  "${backend_smtp_host}" "${backend_smtp_port}"
write_backend_secret secret/kozmik-backend-container \
  "jdbc:postgresql://postgres:5432/${POSTGRES_DB:?required}" \
  "${SMTP_HOST:?required}" "${SMTP_PORT:?required}"

vault kv put secret/kozmik-infrastructure \
  "POSTGRES_USERNAME=${POSTGRES_USER:?required}" \
  "POSTGRES_PASSWORD=${POSTGRES_PASSWORD:?required}" \
  "REDIS_PASSWORD=${REDIS_PASSWORD:?required}" \
  "KEYCLOAK_ADMIN_USERNAME=${KEYCLOAK_ADMIN:?required}" \
  "KEYCLOAK_ADMIN_PASSWORD=${KEYCLOAK_ADMIN_PASSWORD:?required}" \
  "MINIO_ROOT_USER=${MINIO_ROOT_USER:?required}" \
  "MINIO_ROOT_PASSWORD=${MINIO_ROOT_PASSWORD:?required}" \
  "MINIO_EXECUTOR_USER=${MINIO_EXECUTOR_USER:?required}" \
  "MINIO_EXECUTOR_PASSWORD=${MINIO_EXECUTOR_PASSWORD:?required}" \
  "MINIO_INGEST_USER=${MINIO_INGEST_USER:?required}" \
  "MINIO_INGEST_PASSWORD=${MINIO_INGEST_PASSWORD:?required}" >/dev/null

vault kv put secret/kozmik-keycloak \
  "KC_DB_USERNAME=${POSTGRES_USER:?required}" \
  "KC_DB_PASSWORD=${POSTGRES_PASSWORD:?required}" \
  "KC_BOOTSTRAP_ADMIN_USERNAME=${KEYCLOAK_ADMIN:?required}" \
  "KC_BOOTSTRAP_ADMIN_PASSWORD=${KEYCLOAK_ADMIN_PASSWORD:?required}" \
  "KEYCLOAK_BACKEND_CLIENT_SECRET=${KEYCLOAK_BACKEND_CLIENT_SECRET:?required}" \
  "DEMO_REPORTER_PASSWORD=${DEMO_REPORTER_PASSWORD:?required}" \
  "DEMO_SCIENTIST_PASSWORD=${DEMO_SCIENTIST_PASSWORD:?required}" \
  "DEMO_ADMIN_PASSWORD=${DEMO_ADMIN_PASSWORD:?required}" \
  "SMTP_HOST=${SMTP_HOST:?required}" \
  "SMTP_PORT=${SMTP_PORT:?required}" \
  "SMTP_FROM=${SMTP_FROM:?required}" \
  "SMTP_FROM_DISPLAY_NAME=${SMTP_FROM_DISPLAY_NAME:?required}" \
  "SMTP_AUTH=${SMTP_AUTH:?required}" \
  "SMTP_STARTTLS=${SMTP_STARTTLS:?required}" \
  "SMTP_SSL=${SMTP_SSL:?required}" \
  "SMTP_USERNAME=${SMTP_USERNAME:-}" \
  "SMTP_PASSWORD=${SMTP_PASSWORD:-}" >/dev/null

if [ -n "${OPENAI_COMPATIBLE_API_KEY:-}" ]; then
  vault kv put secret/kozmik-executor \
    "INTERNAL_API_KEY=${INTERNAL_API_KEY}" \
    "KAFKA_MESSAGE_SIGNING_KEY=${KAFKA_MESSAGE_SIGNING_KEY}" \
    "MINIO_ACCESS_KEY=${MINIO_EXECUTOR_USER}" \
    "MINIO_SECRET_KEY=${MINIO_EXECUTOR_PASSWORD}" \
    "OPENAI_COMPATIBLE_API_KEY=${OPENAI_COMPATIBLE_API_KEY}" >/dev/null
  echo "Vault initialized with runtime secrets and an OpenAI-compatible secret."
else
  vault kv put secret/kozmik-executor \
    "INTERNAL_API_KEY=${INTERNAL_API_KEY}" \
    "KAFKA_MESSAGE_SIGNING_KEY=${KAFKA_MESSAGE_SIGNING_KEY}" \
    "MINIO_ACCESS_KEY=${MINIO_EXECUTOR_USER}" \
    "MINIO_SECRET_KEY=${MINIO_EXECUTOR_PASSWORD}" >/dev/null
  echo "Vault initialized with runtime secrets; no OpenAI-compatible secret was supplied."
fi
