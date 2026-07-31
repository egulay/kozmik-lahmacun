#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

require_command docker
require_command curl
require_env_file

# shellcheck disable=SC1090
set -a
source "${ENV_FILE}"
set +a

compose exec -T postgres pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"
compose exec -T postgres psql \
  --username "${POSTGRES_USER}" \
  --dbname postgres \
  --tuples-only \
  --no-align \
  --command "SELECT datname FROM pg_database WHERE datname = '${KEYCLOAK_DB:-keycloak}'" \
  | grep -qx "${KEYCLOAK_DB:-keycloak}"
compose exec -T redis redis-cli -a "${REDIS_PASSWORD}" --no-auth-warning ping | grep -q PONG
compose exec -T vault vault status >/dev/null
curl --fail --silent --show-error \
  "http://localhost:${MAILPIT_UI_PORT:-8025}/readyz" >/dev/null
compose exec -T \
  -e VAULT_ADDR=http://127.0.0.1:8200 \
  -e VAULT_TOKEN="${VAULT_BACKEND_TOKEN}" \
  vault vault kv metadata get secret/kozmik-backend >/dev/null
compose exec -T \
  -e VAULT_ADDR=http://127.0.0.1:8200 \
  -e VAULT_TOKEN="${VAULT_DEV_ROOT_TOKEN_ID}" \
  vault vault kv metadata get secret/kozmik-infrastructure >/dev/null
compose exec -T \
  -e VAULT_ADDR=http://127.0.0.1:8200 \
  -e VAULT_TOKEN="${VAULT_DEV_ROOT_TOKEN_ID}" \
  vault vault kv metadata get secret/kozmik-keycloak >/dev/null
for smtp_field in SMTP_HOST SMTP_PORT SMTP_FROM SMTP_FROM_DISPLAY_NAME \
  SMTP_AUTH SMTP_STARTTLS SMTP_SSL SMTP_USERNAME SMTP_PASSWORD; do
  compose exec -T \
    -e VAULT_ADDR=http://127.0.0.1:8200 \
    -e VAULT_TOKEN="${VAULT_DEV_ROOT_TOKEN_ID}" \
    vault vault kv get -field="${smtp_field}" secret/kozmik-keycloak >/dev/null
done

readonly expected_topics=(
  "execution.commands.v1"
  "execution.events.v1"
  "execution.results.v1"
  "execution.commands.v1.dlt"
  "execution.events.v1.dlt"
  "execution.results.v1.dlt"
  "ingestion.events.v1"
  "ingestion.status.v1"
  "ingestion.events.v1.dlt"
  "ingestion.status.v1.dlt"
  "ingestion.records.v1"
  "ingestion.records.v1.dlt"
  "ingestion.stream.status.v1"
  "ingestion.stream.status.v1.dlt"
)
topic_list="$(compose exec -T kafka /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 --list)"
for topic in "${expected_topics[@]}"; do
  grep -qx "${topic}" <<<"${topic_list}"
done

readonly expected_buckets=(raw refined models results)
bucket_list="$(compose run --rm --no-deps --entrypoint /bin/sh minio-init -c \
  'mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null && mc ls local')"
for bucket in "${expected_buckets[@]}"; do
  grep -q "${bucket}/" <<<"${bucket_list}"
done
compose run --rm --no-deps --entrypoint /bin/sh minio-init -c \
  'mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null && mc event list local/raw' \
  | grep -q 'arn:minio:sqs::PRIMARY:kafka'

realm_json="$(curl --fail --silent --show-error \
  "http://localhost:${KEYCLOAK_PORT}/realms/kozmik/.well-known/openid-configuration")"
grep -q '"issuer":"http://localhost:' <<<"${realm_json}"

admin_token="$(curl --fail --silent --show-error \
  --data-urlencode "client_id=admin-cli" \
  --data-urlencode "username=${KEYCLOAK_ADMIN}" \
  --data-urlencode "password=${KEYCLOAK_ADMIN_PASSWORD}" \
  --data-urlencode "grant_type=password" \
  "http://localhost:${KEYCLOAK_PORT}/realms/master/protocol/openid-connect/token" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')"

roles_json="$(curl --fail --silent --show-error \
  -H "Authorization: Bearer ${admin_token}" \
  "http://localhost:${KEYCLOAK_PORT}/admin/realms/kozmik/roles")"
clients_json="$(curl --fail --silent --show-error \
  -H "Authorization: Bearer ${admin_token}" \
  "http://localhost:${KEYCLOAK_PORT}/admin/realms/kozmik/clients?clientId=kozmik-backend")"
python3 -c '
import json, sys
roles = {role["name"] for role in json.loads(sys.argv[1])}
assert {"REPORTER", "SCIENTIST", "ADMIN"} <= roles
clients = json.loads(sys.argv[2])
assert len(clients) == 1 and clients[0]["clientId"] == "kozmik-backend"
' "${roles_json}" "${clients_json}"

echo "Infrastructure smoke verification passed."
