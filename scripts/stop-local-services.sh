#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"
require_env_file

if ! command -v lsof >/dev/null 2>&1; then
  echo "lsof is required to stop previous local development services." >&2
  exit 1
fi

stop_repository_listener() {
  local service="$1"
  local port="$2"
  local pid
  local process_directory

  while IFS= read -r pid; do
    [[ -n "${pid}" ]] || continue
    process_directory="$(lsof -a -p "${pid}" -d cwd -Fn 2>/dev/null \
      | sed -n 's/^n//p' | head -1)"
    if [[ "${process_directory}" != "${REPOSITORY_ROOT}"* ]]; then
      echo "Port ${port} is occupied by PID ${pid} outside this repository." >&2
      echo "Refusing to stop an unrelated process (${process_directory:-unknown directory})." >&2
      exit 1
    fi

    echo "Stopping previous ${service} process (PID ${pid}, port ${port})..."
    kill -TERM "${pid}"
    for _ in {1..25}; do
      if ! kill -0 "${pid}" 2>/dev/null; then
        break
      fi
      sleep 0.2
    done
    if kill -0 "${pid}" 2>/dev/null; then
      echo "${service} did not stop gracefully; forcing repository PID ${pid} down."
      kill -KILL "${pid}"
    fi
  done < <(lsof -nP -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true)
}

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

stop_repository_listener "Java backend" "${BACKEND_PORT:-8080}"
stop_repository_listener "Python executor" "${EXECUTOR_PORT:-8000}"
stop_repository_listener "SvelteKit frontend" "${FRONTEND_PORT:-5173}"
