# Privacy-safe result explanation

Result explanation is a non-critical step after Spark has produced durable artifacts and bounded
result data. Python constructs a new allowlisted facts object containing only:

- execution type, requested language, row count, and registered ML algorithm name;
- at most 20 KPI or metric codes, label keys, scalar values, and units;
- at most 20 warning codes and message keys.

The preview object, preview rows, chart data, direct identifiers, artifact paths, and unapproved
fields are never passed to the provider. The serialized facts object is limited to 12,000
characters and the generated summary to 4,000 characters.

The provider is selected from Java's effective configuration. It receives an instruction to
write concise management-oriented Turkish or English and not infer unsupported causes or
identities.

Java persists `summaryStatus` as `COMPLETED` or `FAILED`. A provider timeout, invalid response,
empty response, or size violation produces `FAILED` with no summary text. It does not change the
completed execution, result preview, metrics, or artifact availability.
