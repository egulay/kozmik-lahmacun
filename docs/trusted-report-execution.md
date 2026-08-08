# Trusted report execution

Validated report orders are consumed from Kafka and mapped only through explicit Spark
filter, aggregation, temporal-grouping and numeric-range-grouping registries. Numeric bands
are represented as validated, contiguous and non-overlapping bucket definitions and become
trusted Spark column expressions; they are never translated from arbitrary SQL. Dataset
location and format come from Java's immutable
effective-configuration snapshot; an order cannot supply SQL, Python, modules, or an artifact
path.

The governed single-entity expression contract supports distinct projection,
null replacement, typed arithmetic, basic string transformations, date
extraction and day arithmetic, global top-N, median/percentile, variance and
standard deviation. Division by zero produces null. Percentiles use Spark's
approved approximate-percentile implementation and must be interpreted as
approximate analytical values. Filtered aggregations provide conditional
aggregation without generated SQL.

Window functions, per-group ranking, running or moving calculations, pivoting,
joins, unions and arbitrary structured-data paths are not part of this contract
and must not be silently approximated by planning.

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
