#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

"${REPOSITORY_ROOT}/scripts/verify-static.sh"

(cd "${REPOSITORY_ROOT}/backend" \
  && mvn --batch-mode -Dmaven.repo.local="${REPOSITORY_ROOT}/backend/.m2" verify)

if [[ ! -x "${REPOSITORY_ROOT}/executor/.venv/bin/python" ]]; then
  python3 -m venv "${REPOSITORY_ROOT}/executor/.venv"
fi
"${REPOSITORY_ROOT}/executor/.venv/bin/pip" install --quiet -e "${REPOSITORY_ROOT}/executor[dev]"
(cd "${REPOSITORY_ROOT}/executor" \
  && .venv/bin/ruff check . \
  && .venv/bin/pytest)

(cd "${REPOSITORY_ROOT}/frontend" \
  && npm install --cache .npm \
  && npm run check \
  && npm test \
  && npm run build \
  && npm run test:e2e)

echo "All repository checks passed."
