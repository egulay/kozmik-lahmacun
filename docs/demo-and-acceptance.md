# Demo and acceptance

Start the complete clean local platform:

```bash
./scripts/start-all.sh
```

Then generate and ingest all deterministic datasets:

```bash
./scripts/seed-demo-data.sh
```

This creates an ignored `demo/generated/` directory containing exactly
1,000,000 telecom CDR rows, 50,000 sales rows, and 100,000 payment transaction
rows. The generator uses one deterministic process per dataset by default;
`--workers 1` remains available for constrained environments and produces
byte-identical files.

The Sales and Payment Transactions CSV files are uploaded to MinIO using their
governed entity UUID filenames. MinIO `ObjectCreated` publishes to Kafka and
starts the file-ingestion path for each object.

After both file notifications are emitted, the seed publisher sends the CDR
chunks without waiting for either file import to finish. File and stream
ingestion can therefore progress concurrently, subject to the executor's
configured Spark concurrency limit.

The CDR CSV is never uploaded to the raw bucket. The seed publisher reads it in
bounded chunks and publishes signed `StreamIngestionChunk` envelopes to
`ingestion.records.v1`. Each envelope carries the CDR entity UUID and its schema
descriptor. The continuously
running Python CDR consumer resolves the schema from Java and writes immutable
Parquet parts under one governed dataset prefix. Java persists an `ACTIVE`
stream, completed micro-batches, cumulative rows, Kafka checkpoint, and
watermark. The finite demo waits for one million committed rows but never marks
the stream completed. Neither ingestion path polls MinIO.

Role scenarios live in `demo/scenarios/`. Reporter scenarios are reports only,
Scientist scenarios describe approved ML requests, and the
Admin scenario covers signed restart, drain, replay rejection, and
configuration reload.

Run the complete acceptance gate:

```bash
./scripts/demo-acceptance.sh
```

The gate verifies exact data volumes, builds all services, runs Java
Testcontainers integration tests, Python Spark/privacy tests, Svelte checks,
component tests, production build, and Playwright bilingual UI tests.
