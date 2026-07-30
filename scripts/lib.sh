#!/usr/bin/env bash

set -euo pipefail

REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly REPOSITORY_ROOT
readonly COMPOSE_FILE="${REPOSITORY_ROOT}/infrastructure/compose.yaml"
readonly ENV_FILE="${REPOSITORY_ROOT}/.env"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Required command not found: $1" >&2
    exit 1
  fi
}

require_env_file() {
  if [[ ! -f "${ENV_FILE}" ]]; then
    echo "Missing .env. Run ./scripts/setup-env.sh first." >&2
    exit 1
  fi
}

load_deployment_secrets() {
  local secret_file="${KOZMIK_SECRETS_FILE:-}"
  if [[ -z "${secret_file}" ]]; then
    return 0
  fi
  if [[ ! -f "${secret_file}" ]]; then
    echo "KOZMIK_SECRETS_FILE does not identify a readable file." >&2
    exit 1
  fi
  local permissions
  permissions="$(stat -f '%Lp' "${secret_file}" 2>/dev/null \
    || stat -c '%a' "${secret_file}" 2>/dev/null)"
  if [[ "${permissions}" != "600" && "${permissions}" != "400" ]]; then
    echo "Deployment secret file must have permissions 600 or 400." >&2
    exit 1
  fi
  set -a
  # shellcheck disable=SC1090
  source "${secret_file}"
  set +a
  echo "Loaded one-time deployment secrets from a protected file."
}

compose() {
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" "$@"
}
