#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

require_command docker
require_command curl

"${REPOSITORY_ROOT}/scripts/setup-env.sh"
require_env_file
"${REPOSITORY_ROOT}/scripts/check-demo-baseline.sh"

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a
load_deployment_secrets

# API keys are accepted only from the launching environment or the protected,
# one-time deployment file. They are never persisted by local setup.
exported_openai_api_key="${OPENAI_COMPATIBLE_API_KEY:-${OPENAI_API_KEY:-}}"

if [[ -n "${exported_openai_api_key}" ]]; then
  export OPENAI_COMPATIBLE_API_KEY="${exported_openai_api_key}"
  export LLM_PROVIDER="OPENAI_COMPATIBLE"
  echo "OpenAI-compatible provider selected; the exported API key will be written to Vault."
else
  unset OPENAI_COMPATIBLE_API_KEY OPENAI_API_KEY
  export LLM_PROVIDER="LM_STUDIO"
  echo "No exported OpenAI API key found; LM Studio provider selected."
fi

# The executor credential has one canonical source. Compatibility aliases are
# exported for the Python MinIO client and must never drift independently.
export MINIO_ACCESS_KEY="${MINIO_EXECUTOR_USER}"
export MINIO_SECRET_KEY="${MINIO_EXECUTOR_PASSWORD}"

# One deliberately predictable, policy-compliant credential for all disposable
# local-demo users. It overrides generated .env values only for clean-demo startup.
readonly DEMO_USER_PASSWORD="Demo1234!"
export DEMO_REPORTER_PASSWORD="${DEMO_USER_PASSWORD}"
export DEMO_SCIENTIST_PASSWORD="${DEMO_USER_PASSWORD}"
export DEMO_ADMIN_PASSWORD="${DEMO_USER_PASSWORD}"

echo "Stopping previous local Java, Python, and SvelteKit processes..."
"${REPOSITORY_ROOT}/scripts/stop-local-services.sh"

echo "Removing the complete local demo stack and all named volumes..."
compose --profile full-demo --profile application down --volumes --remove-orphans

echo "Starting and initializing PostgreSQL, Redis, Kafka, MinIO, and Keycloak..."
"${REPOSITORY_ROOT}/scripts/dev-up.sh"

echo "Recreating the application database schema from ddl.sql..."
compose --profile full-demo run --rm --no-deps database-reset

echo "Opening infrastructure logs and starting Java..."
backend_log="${JAVA_LOG_DIR}"
if [[ "${backend_log}" != /* ]]; then
  backend_log="${REPOSITORY_ROOT}/${backend_log}"
fi
backend_log="${backend_log}/$(date +%Y-%m)/$(date +%Y-%m-%d).log"
backend_log_start_size=0
if [[ -f "${backend_log}" ]]; then
  backend_log_start_size="$(wc -c < "${backend_log}" | tr -d ' ')"
fi
if ! "${REPOSITORY_ROOT}/scripts/open-service-consoles.sh" infrastructure java; then
  echo "Could not open infrastructure and Java tabs." >&2
  exit 1
fi

echo "Waiting for the Java control plane..."
backend_deadline=$((SECONDS + 180))
until curl --fail --silent "http://localhost:${BACKEND_PORT:-8080}/actuator/health/liveness" >/dev/null; do
  if [[ -f "${backend_log}" ]] \
      && tail -c "+$((backend_log_start_size + 1))" "${backend_log}" \
          | grep -Eq "Application run failed|APPLICATION FAILED TO START"; then
    echo "Java backend exited during startup. Recent errors:" >&2
    tail -n 40 "${backend_log}" >&2
    echo "See the Kozmik Java iTerm tab and ${backend_log}" >&2
    exit 1
  fi
  if (( SECONDS >= backend_deadline )); then
    echo "Java backend did not become healthy within 180 seconds." >&2
    echo "See the Kozmik Java iTerm tab and ${backend_log}" >&2
    exit 1
  fi
  sleep 2
done

echo "Java control plane is healthy. Starting Python executor..."
if ! "${REPOSITORY_ROOT}/scripts/open-service-consoles.sh" python; then
  echo "Could not open the Python executor tab." >&2
  exit 1
fi

echo "Waiting for the Python executor..."
executor_deadline=$((SECONDS + 180))
until curl --fail --silent \
  --header "X-Internal-API-Key: ${INTERNAL_API_KEY}" \
  "http://localhost:${EXECUTOR_PORT:-8000}/internal/v1/health" >/dev/null; do
  if (( SECONDS >= executor_deadline )); then
    echo "Python executor did not become healthy." >&2
    exit 1
  fi
  sleep 2
done

echo "Python executor is healthy. Starting SvelteKit frontend..."
if ! "${REPOSITORY_ROOT}/scripts/open-service-consoles.sh" frontend; then
  echo "Could not open the SvelteKit frontend tab." >&2
  exit 1
fi

echo "Waiting for the SvelteKit frontend..."
frontend_deadline=$((SECONDS + 120))
until curl --fail --silent "http://localhost:${FRONTEND_PORT:-5173}/" >/dev/null; do
  if (( SECONDS >= frontend_deadline )); then
    echo "Frontend did not become healthy." >&2
    exit 1
  fi
  sleep 2
done

"${REPOSITORY_ROOT}/scripts/full-demo-smoke.sh" --require-empty-entities

compose ps --all
echo
echo "Clean demo is ready: http://localhost:${FRONTEND_PORT:-5173}"
echo "Demo email inbox:  http://localhost:${MAILPIT_UI_PORT:-8025}"
if command -v open >/dev/null 2>&1; then
  open "http://localhost:${MAILPIT_UI_PORT:-8025}" >/dev/null 2>&1 || true
fi
echo
echo "Demo login credentials (local environment only):"
echo "  Reporter  username: reporter   password: ${DEMO_REPORTER_PASSWORD}"
echo "  Scientist username: scientist  password: ${DEMO_SCIENTIST_PASSWORD}"
echo "  Admin     username: admin      password: ${DEMO_ADMIN_PASSWORD}"
echo
echo "These predictable credentials are only for the disposable local demo realm."
echo "Next: ./scripts/seed-demo-data.sh"
