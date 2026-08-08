#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

require_command docker
require_command python3
require_env_file

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

readonly cdr_entity_id="22222222-2222-4222-8222-222222222222"
readonly sales_entity_id="11111111-1111-4111-8111-111111111111"
readonly payment_entity_id="33333333-3333-4333-8333-333333333333"
readonly employee_entity_id="44444444-4444-4444-8444-444444444444"
readonly import_date="20260728"
readonly generated_directory="${REPOSITORY_ROOT}/demo/generated"
readonly cdr_source="${generated_directory}/cdr.csv"
readonly sales_source="${generated_directory}/sales_${sales_entity_id}_${import_date}.csv"
readonly payment_source="${generated_directory}/payment_transactions_${payment_entity_id}_${import_date}.csv"
readonly employee_source="${generated_directory}/employee_records_${employee_entity_id}_${import_date}.csv"
sales_object="$(basename "${sales_source}")"
readonly sales_object
payment_object="$(basename "${payment_source}")"
readonly payment_object
employee_object="$(basename "${employee_source}")"
readonly employee_object
readonly executor_python="${REPOSITORY_ROOT}/executor/.venv/bin/python"

echo "Verifying the running platform before data seeding..."
"${REPOSITORY_ROOT}/scripts/full-demo-smoke.sh"

if ! python3 - "${KAFKA_PORT:-9092}" <<'PY'
import socket
import sys

try:
    with socket.create_connection(("127.0.0.1", int(sys.argv[1])), timeout=3):
        pass
except OSError:
    raise SystemExit(1)
PY
then
  echo "Kafka is not reachable at localhost:${KAFKA_PORT:-9092}. Run ./start-all.sh and retry." >&2
  exit 1
fi

echo "Generating deterministic CDR, sales, payment transaction, and employee CSV datasets..."
python3 "${REPOSITORY_ROOT}/demo/generate_data.py" \
  --output "${generated_directory}" \
  --cdr-rows 1000000 \
  --sales-rows 50000 \
  --payment-rows 100000 \
  --employee-rows 50000

completed_import_exists() {
  local object_name="$1"
  local count
  count="$(compose exec -T postgres psql \
    --username "${POSTGRES_USER}" \
    --dbname "${POSTGRES_DB}" \
    --tuples-only \
    --no-align \
    --command "SELECT count(*) FROM kozmik_lahmacun.import_job WHERE source_reference LIKE '%/${object_name}' AND status = 'COMPLETED'")"
  (( count > 0 ))
}

upload_if_needed() {
  local source_file="$1"
  local object_name="$2"
  if completed_import_exists "${object_name}"; then
    echo "${object_name} is already governed and complete; skipping upload."
    return
  fi
  echo "Uploading ${object_name} to MinIO raw/incoming..."
  compose run --rm --no-deps --entrypoint /bin/sh minio-init -c '
    set -eu
    mc alias set ingest-root http://minio:9000 "${MINIO_ROOT_USER}" "${MINIO_ROOT_PASSWORD}" >/dev/null
    mc admin policy create ingest-root kozmik-ingest /opt/kozmik/ingest-policy.json >/dev/null
    mc admin user add ingest-root "${MINIO_INGEST_USER}" "${MINIO_INGEST_PASSWORD}" >/dev/null
    if ! attach_output="$(mc admin policy attach ingest-root kozmik-ingest --user "${MINIO_INGEST_USER}" 2>&1)"; then
      case "${attach_output}" in
        *"policy change is already in effect"*|*"policy update has no net effect"*) ;;
        *)
          echo "${attach_output}" >&2
          exit 1
          ;;
      esac
    fi
    mc alias set uploader http://minio:9000 "${MINIO_INGEST_USER}" "${MINIO_INGEST_PASSWORD}" >/dev/null
    mc pipe "uploader/raw/incoming/$1"
  ' seed-upload "${object_name}" < "${source_file}"
}

upload_if_needed "${sales_source}" "${sales_object}"
upload_if_needed "${payment_source}" "${payment_object}"
upload_if_needed "${employee_source}" "${employee_object}"

wait_for_import() {
  local object_name="$1"
  local deadline=$((SECONDS + 900))
  local status=""
  while (( SECONDS < deadline )); do
    status="$(compose exec -T postgres psql \
      --username "${POSTGRES_USER}" \
      --dbname "${POSTGRES_DB}" \
      --tuples-only \
      --no-align \
      --command "SELECT status FROM kozmik_lahmacun.import_job WHERE source_reference LIKE '%/${object_name}' ORDER BY created_at DESC LIMIT 1")"
    status="${status//[[:space:]]/}"
    case "${status}" in
      COMPLETED)
        return
        ;;
      FAILED)
        compose exec -T postgres psql \
          --username "${POSTGRES_USER}" \
          --dbname "${POSTGRES_DB}" \
          --command "SELECT source_reference, status, error_code, error_message FROM kozmik_lahmacun.import_job WHERE source_reference LIKE '%/${object_name}' ORDER BY created_at DESC LIMIT 1"
        echo "Governed ingestion failed for ${object_name}." >&2
        exit 1
        ;;
    esac
    sleep 5
  done
  echo "Timed out waiting for governed ingestion of ${object_name}." >&2
  exit 1
}

if [[ ! -x "${executor_python}" ]]; then
  echo "Python executor environment is missing. Run ./scripts/start-all.sh first." >&2
  exit 1
fi

cdr_stream_id="$(compose exec -T postgres psql \
  --username "${POSTGRES_USER}" \
  --dbname "${POSTGRES_DB}" \
  --tuples-only \
  --no-align \
  --command "SELECT id FROM kozmik_lahmacun.ingestion_stream WHERE entity_id = '${cdr_entity_id}'::uuid AND status = 'COMPLETED' AND cumulative_rows = 1000000 ORDER BY updated_at DESC LIMIT 1")"
cdr_stream_id="${cdr_stream_id//[[:space:]]/}"
if [[ -n "${cdr_stream_id}" ]]; then
  echo "A completed 1,000,000-row CDR stream already exists; skipping Kafka publication."
else
  echo "Publishing CDR example records to generic Kafka ingestion.records.v1..."
  cdr_publish_output="$("${executor_python}" "${REPOSITORY_ROOT}/demo/publish_cdr.py" \
    --csv "${cdr_source}" \
    --entity-id "${cdr_entity_id}" \
    --bootstrap-servers "localhost:${KAFKA_PORT:-9092}" \
    --topic "ingestion.records.v1" \
    --chunk-size 5000)"
  echo "${cdr_publish_output}"
  cdr_stream_id="$(sed -n 's/^CDR_STREAM_ID=//p' <<< "${cdr_publish_output}")"
  if [[ -z "${cdr_stream_id}" ]]; then
    echo "CDR publisher did not return a stream identifier." >&2
    exit 1
  fi
fi

# File-ingestion events are already active while the CDR chunks are
# published. The executor's configured Spark concurrency limit remains the
# authoritative resource boundary.
echo "Waiting for Sales MinIO ObjectCreated ingestion..."
wait_for_import "${sales_object}"
echo "Waiting for Payment Transactions MinIO ObjectCreated ingestion..."
wait_for_import "${payment_object}"
echo "Waiting for Employee Records MinIO ObjectCreated ingestion..."
wait_for_import "${employee_object}"

echo "Waiting for the governed CDR Kafka stream to reach 1,000,000 rows..."
cdr_deadline=$((SECONDS + 1800))
while (( SECONDS < cdr_deadline )); do
  cdr_status="$(compose exec -T postgres psql \
    --username "${POSTGRES_USER}" \
    --dbname "${POSTGRES_DB}" \
    --tuples-only \
    --no-align \
    --command "SELECT status || ':' || cumulative_rows FROM kozmik_lahmacun.ingestion_stream WHERE id = '${cdr_stream_id}'::uuid")"
  cdr_status="${cdr_status//[[:space:]]/}"
  if [[ "${cdr_status}" == "COMPLETED:1000000" ]]; then
    break
  fi
  if [[ "${cdr_status}" == FAILED:* ]]; then
    echo "Governed CDR stream ingestion failed: ${cdr_status}" >&2
    exit 1
  fi
  sleep 5
done
if [[ "${cdr_status:-}" != "COMPLETED:1000000" ]]; then
  echo "Timed out waiting for governed CDR stream ingestion: ${cdr_status:-missing}" >&2
  exit 1
fi

compose exec -T postgres psql \
  --username "${POSTGRES_USER}" \
  --dbname "${POSTGRES_DB}" \
  --command "SELECT source_reference, status, row_count, refined_bucket, refined_object_key FROM kozmik_lahmacun.import_job WHERE status = 'COMPLETED' ORDER BY created_at"
compose exec -T postgres psql \
  --username "${POSTGRES_USER}" \
  --dbname "${POSTGRES_DB}" \
  --command "SELECT id, source_id, status, cumulative_rows, last_partition, last_offset FROM kozmik_lahmacun.ingestion_stream ORDER BY started_at"

echo "Demo data is ready: 1,000,000 CDR rows, 50,000 sales rows, 100,000 payment transaction rows, and 50,000 employee rows."
"${REPOSITORY_ROOT}/scripts/full-demo-smoke.sh" --require-demo-data
