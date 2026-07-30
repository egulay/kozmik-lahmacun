#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

python3 "${REPOSITORY_ROOT}/demo/generate_data.py" \
  --output "${REPOSITORY_ROOT}/demo/generated" \
  --cdr-rows 1000000 \
  --sales-rows 50000
python3 - "${REPOSITORY_ROOT}/demo/generated" <<'PY'
import csv
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
files = list(root.glob("*.csv"))
counts = {}
for path in files:
    with path.open(encoding="utf-8") as stream:
        counts[path.name] = sum(1 for _ in csv.reader(stream)) - 1
assert counts["cdr.csv"] == 1_000_000, counts
assert counts["sales_11111111-1111-4111-8111-111111111111_20260728.csv"] == 50_000
print("Demo dataset acceptance passed:", counts)
PY
"${REPOSITORY_ROOT}/scripts/test-all.sh"
echo "Milestone 14 acceptance suite passed."
