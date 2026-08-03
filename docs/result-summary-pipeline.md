# Result-summary pipeline

Result summary generation is a non-critical final step after a report or ML execution finishes.
It does not participate in planning, Spark execution, or artifact creation.

The purpose of this stage is narrowly defined: explain the final calculated result in business
language. It does not send the ingested corporate source data to the LLM. Planning is a separate
provider interaction with its own governed metadata contract.

Java derives `includeSummary` from the original English or Turkish request. Summary generation is
enabled by default and remains enabled when the user explicitly asks for one. Explicit negative
phrases such as `exclude summary`, `without a summary`, `özeti dahil etme`, `özet olmasın`, or
`özetsiz` set it to false. Python then skips the LLM call entirely, publishes `summaryStatus` as
`SKIPPED`, and the browser omits the Summary card from both the result page and PDF export.

Examples:

- `Show monthly sales by region without a summary.`
- `Exclude the result summary.`
- `Bölge bazında aylık satışları göster, özeti dahil etme.`
- `Özetsiz bölgesel satış raporu hazırla.`

No inclusion phrase is required. Requests that do not explicitly opt out generate a summary by
default; explicit requests such as `include a summary` or `özeti dahil et` retain that default.

## Contract

Python sends one JSON document to the configured LLM provider containing:

- the original user request;
- requested output language (`en` or `tr`);
- execution type;
- the complete approved structured report or ML order used by the executor;
- the complete governed source-schema metadata supplied by Java, including column names, data
  types, business labels, and bounded categorical vocabularies such as currency codes;
- calculated result schema;
- authoritative total result row count;
- all non-row information rendered by the result screen, including indicators, charts, metrics,
  model-selection information, feature importance, scenarios, and warnings when present;
- every calculated result row when the complete result contains at most 100 rows;
- no result rows when the complete result contains more than 100 rows.

`original user request` is the verbatim request persisted by the Java control plane and carried
separately in the execution command. It is not the planner-generated `order.requestSummary`,
which remains only a concise description of the approved structured order.

The ingested CSV/Kafka records, governed source Parquet dataset, object-storage locations, and
credentials are not attached to this request. The rows described above are rows of the **final
calculated execution result**, not rows copied from the source dataset.

The provider returns plain summary prose. Python removes an optional `Summary`, `Result Summary`,
`Özet`, or `Sonuç Özeti` heading and publishes the remaining text unchanged. There is no claim
model, semantic registry, audit narrative, repair loop, sentence salvage, JSON response wrapper,
or application-level summary-length limit.

## Failure behavior

A provider, serialization, or parsing failure sets `summaryStatus` to `FAILED` and records a typed
`summaryErrorCode`. The completed analytical result, preview, charts, metrics, and artifacts remain
available. Summary failure never changes a successful Spark execution into a failed execution.

Java persists only the result summary status, text, provider, provider model, generation time, and
optional error code. The browser displays `Summary` in English and `Özet` in Turkish.
