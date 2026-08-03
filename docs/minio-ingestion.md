# MinIO event-driven CSV ingestion

Raw CSV objects use this basename convention:

`<entityName>_<entityUUID>_<yyyyMMdd>.csv`

Example:

`sales_11111111-1111-4111-8111-111111111111_20260728.csv`

The demo also uploads:

`payment_transactions_33333333-3333-4333-8333-333333333333_20260728.csv`

Upload under `raw/incoming/`. MinIO publishes only matching `ObjectCreated` notifications to
`ingestion.events.v1`. Python consumes Kafka; it does not poll MinIO and does not run a bucket
watcher.

Python extracts the entity UUID, retrieves the registered structure from Java using the
internal API key, downloads that single object, and applies the exact ordered CSV header and
registered Spark types. String values are trimmed and empty values become null.
The platform ingests supplied values without a stored nullability policy. Failed
type casts become null. Governed Parquet is written to:

`refined/entities/{entityId}/imports/{importId}/data.parquet`

Import lifecycle events are persisted by Java in `import_job` and
`import_status_history`. Re-delivered MinIO and status events are idempotent.

This flow is for file arrivals such as the Sales and Payment Transactions
demos. The payment dataset contains 100,000 deterministic transactions with
account, merchant, channel, geography, device, timestamp, amount, currency,
and synthetic historical fraud-outcome fields. Its fraud outcome is correlated
with realistic risk signals so supervised classification can be demonstrated;
it is synthetic demo evidence, not a production fraud rule.

Telecom CDR streaming
uses the separate `ingestion.records.v1` contract documented in
`docs/streaming-ingestion.md`; stream records are not first copied to MinIO.
