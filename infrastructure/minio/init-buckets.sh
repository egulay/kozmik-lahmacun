#!/bin/sh
set -eu

mc alias set local http://minio:9000 "${MINIO_ROOT_USER}" "${MINIO_ROOT_PASSWORD}"

attach_policy_if_needed() {
  policy="$1"
  user="$2"
  if output="$(mc admin policy attach local "${policy}" --user "${user}" 2>&1)"; then
    return
  fi
  case "${output}" in
    *"policy change is already in effect"*|*"policy update has no net effect"*)
      return
      ;;
    *)
      echo "${output}" >&2
      exit 1
      ;;
  esac
}

for bucket in raw refined models results; do
  mc mb --ignore-existing "local/${bucket}"
done

mc admin policy create local kozmik-executor /opt/kozmik/executor-policy.json
mc admin user add local "${MINIO_EXECUTOR_USER}" "${MINIO_EXECUTOR_PASSWORD}"
attach_policy_if_needed kozmik-executor "${MINIO_EXECUTOR_USER}"

mc admin policy create local kozmik-ingest /opt/kozmik/ingest-policy.json
mc admin user add local "${MINIO_INGEST_USER}" "${MINIO_INGEST_PASSWORD}"
attach_policy_if_needed kozmik-ingest "${MINIO_INGEST_USER}"

notification_arn="arn:minio:sqs::PRIMARY:kafka"
mc event add local/raw "${notification_arn}" --ignore-existing --event put \
  --prefix incoming/ --suffix .csv

mc ls local
mc event list local/raw
