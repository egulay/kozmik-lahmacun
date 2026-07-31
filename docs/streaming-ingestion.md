# Governed generic streaming ingestion

`ingestion.records.v1` is the generic continuous ingestion topic for producers
such as GSM towers, HR systems, XDR sources, or IoT devices. Kafka contains
bounded chunks of records, not a CSV object-created notification.

Each signed version `1.0` chunk contains:

- `chunkId` for idempotency;
- `streamId` for the continuous import/dataset identity;
- `entity.id` plus the proposed normalized entity and column schema;
- optional bounded `categoricalValues` for string columns whose exact domain is
  known by the producer;
- bounded `sourceId`, `sequence`, and `producedAt` metadata;
- between 1 and 5,000 stream records.

Python verifies the HMAC envelope and asks a secured Java internal API to
resolve the entity. If the UUID already exists, Java returns its registered
structure and rejects structural drift. If it does not exist, Java
transactionally creates one `business_entity` and its normalized immutable
`entity_column` records using the configured ingestion-system identity.
Categorical vocabulary is stored separately as normalized column metadata and
may grow only within the governed 32-value bound. It is supplied to planning so
business terms can be resolved to exact stored values; unmatched values are
rejected before execution rather than silently producing an empty result.
Python then enforces exact column
order and registered Spark types,
and writes each chunk as an immutable Parquet part under:

`refined/entities/{entityId}/streams/{streamId}/dataset/part-{sequence}-{chunkId}.parquet`

Java persists the long-lived source in `ingestion_stream`. Its status is
`INGESTING` while a chunk is in flight and `COMPLETED` after the latest chunk
is durably stored; a later chunk moves it back to `INGESTING`. Every finite chunk is recorded
separately in `ingestion_stream_batch`, and append-only lifecycle events are
stored in `ingestion_stream_event`. Signed progress arrives on `ingestion.stream.status.v1`
and advances cumulative rows and the Kafka partition/offset checkpoint.

Kafka offsets are committed after the chunk is processed. Replayed chunks do
not rewrite data; their deterministic completion event may be republished and
is deduplicated by Java.

When a report or ML execution starts, Java creates an immutable
`execution_stream_binding` containing the committed `throughSequence`,
`throughOffset`, and snapshot row count. Python downloads only Parquet parts at
or below that sequence. Records arriving later remain available to future
executions but cannot change an already-bound execution.
