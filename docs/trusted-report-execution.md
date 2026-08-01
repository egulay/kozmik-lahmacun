# Trusted report execution

Validated report orders are consumed from Kafka and mapped only through the explicit Spark
filter and aggregation registries. Dataset location and format come from Java's immutable
effective-configuration snapshot; an order cannot supply SQL, Python, modules, or an artifact
path.

The worker bounds concurrency with `SPARK_MAX_CONCURRENT_JOBS` (default `4`) and applies the
lower of the order and platform timeouts. Timeout or task cancellation sets the cooperative
cancellation hook and cancels the Spark job group.

The same governed execution implementation supports an operator-configured Spark master.
`executor/config/spark.yml` owns the master, Hive switch, and validated `spark.*` property
map. Standalone, YARN, and Kubernetes environments can use that file together with their
normal external authentication configuration. Allow-listed `SPARK_*` environment variables
can override deployment-specific resource values. Execution orders and LLM output cannot
change cluster resources or inject arbitrary Spark properties.

Full results are written as a single Parquet object under
`results/executions/{executionId}/{artifactId}.parquet`. Kafka carries only bounded preview,
KPI, chart, warning, and artifact metadata. Java validates and registers that metadata
transactionally, then emits `execution-result-ready` over the existing execution SSE stream.

`GET /api/executions/{executionId}/result` is ownership-protected. Reporters receive governed
preview guidance. Scientists and Admins receive Jupyter guidance; direct artifact download is
intentionally not exposed in this milestone.
