#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

require_command docker
require_env_file

if [[ "${1:-}" == "--volumes" ]]; then
  compose down --volumes --remove-orphans
elif [[ $# -eq 0 ]]; then
  compose down --remove-orphans
else
  echo "Usage: $0 [--volumes]" >&2
  exit 2
fi

