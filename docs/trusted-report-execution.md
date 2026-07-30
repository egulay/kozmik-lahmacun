# Trusted report execution

Validated report orders are consumed from Kafka and mapped only through the explicit Spark
filter and aggregation registries. Dataset location and format come from Java's immutable
effective-configuration snapshot; an order cannot supply SQL, Python, modules, or an artifact
path.

The worker bounds concurrency with `SPARK_MAX_CONCURRENT_JOBS` (default `8`) and applies the
lower of the order and platform timeouts. Timeout or task cancellation sets the cooperative
cancellation hook and cancels the Spark job group.

Full results are written as a single Parquet object under
`results/executions/{executionId}/{artifactId}.parquet`. Kafka carries only bounded preview,
KPI, chart, warning, and artifact metadata. Java validates and registers that metadata
transactionally, then emits `execution-result-ready` over the existing execution SSE stream.

`GET /api/executions/{executionId}/result` is ownership-protected. Reporters receive governed
preview guidance. Scientists and Admins receive Jupyter guidance; direct artifact download is
intentionally not exposed in this milestone.
