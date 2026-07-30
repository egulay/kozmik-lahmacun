#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

require_command docker
require_env_file

echo "Stopping local Java, Python, and SvelteKit processes..."
"${REPOSITORY_ROOT}/scripts/stop-local-services.sh"

echo "Stopping and removing the complete local demo Docker stack..."
compose \
  --profile full-demo \
  --profile application \
  down \
  --volumes \
  --remove-orphans

echo "Kozmik Lahmacun local demo stopped."
echo "Project containers, networks, and named volumes have been removed."
echo "The repository .env and generated demo files were retained."
