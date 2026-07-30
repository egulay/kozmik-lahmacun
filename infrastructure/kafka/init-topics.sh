#!/usr/bin/env bash
set -euo pipefail

readonly bootstrap_server="kafka:29092"
readonly metric_name_warning="Due to limitations in metric names"
readonly topics=(
  "execution.commands.v1"
  "execution.events.v1"
  "execution.results.v1"
  "execution.control.v1"
  "execution.commands.v1.dlt"
  "execution.events.v1.dlt"
  "execution.results.v1.dlt"
  "execution.control.v1.dlt"
  "ingestion.events.v1"
  "ingestion.status.v1"
  "ingestion.events.v1.dlt"
  "ingestion.status.v1.dlt"
  "ingestion.records.v1"
  "ingestion.records.v1.dlt"
  "ingestion.stream.status.v1"
  "ingestion.stream.status.v1.dlt"
)

for topic in "${topics[@]}"; do
  set +e
  topic_output="$(/opt/kafka/bin/kafka-topics.sh \
    --bootstrap-server "${bootstrap_server}" \
    --create \
    --if-not-exists \
    --topic "${topic}" \
    --partitions 1 \
    --replication-factor 1 2>&1)"
  topic_result=$?
  set -e
  printf '%s\n' "${topic_output}" \
    | awk -v warning="${metric_name_warning}" 'index($0, warning) == 0'
  if (( topic_result != 0 )); then
    exit "${topic_result}"
  fi
done

/opt/kafka/bin/kafka-topics.sh --bootstrap-server "${bootstrap_server}" --list
