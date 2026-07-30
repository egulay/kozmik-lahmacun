#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

require_command docker
require_env_file
load_deployment_secrets

compose config --quiet
compose up --detach --wait --wait-timeout 180 vault postgres redis kafka mailpit

compose run --rm --no-deps postgres-init
compose run --rm --no-deps vault-init

# Keycloak itself has no Spring Vault integration. Resolve its SMTP runtime
# environment from the just-initialized Vault path without printing secrets.
vault_keycloak_field() {
  compose exec -T vault sh -c \
    'VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN="$VAULT_DEV_ROOT_TOKEN_ID" \
      vault kv get -field="$1" secret/kozmik-keycloak' sh "$1"
}
for smtp_key in SMTP_HOST SMTP_PORT SMTP_FROM SMTP_FROM_DISPLAY_NAME \
  SMTP_AUTH SMTP_STARTTLS SMTP_SSL SMTP_USERNAME SMTP_PASSWORD; do
  printf -v "${smtp_key?}" '%s' "$(vault_keycloak_field "${smtp_key}")"
  export "${smtp_key}"
done

compose up --detach --no-deps --wait --wait-timeout 180 keycloak

compose run --rm --no-deps kafka-init

compose up --detach --no-deps --wait --wait-timeout 180 minio
compose run --rm --no-deps minio-init

compose ps --all
echo "Local infrastructure is healthy and initialized."
