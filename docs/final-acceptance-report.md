# Milestone 14 final acceptance report

Date: 2026-07-28  
Result: **PASS**

## Accepted scope

| Capability | Evidence |
| --- | --- |
| Telecom CDR demo | Deterministic generator produced exactly 1,000,000 rows (81 MiB) |
| Sales demo | Deterministic generator produced exactly 50,000 rows (3.2 MiB) |
| Batch CDR ingestion | Spark validates the fixed CDR schema and writes governed Parquet to MinIO |
| Event-driven sales ingestion | Filename-contract upload uses MinIO `ObjectCreated` -> Kafka; no polling |
| Reporter scenarios | Turkish sales and English CDR governed-report scenarios |
| Scientist scenarios | Approved deterministic linear-regression scenarios for sales and CDR |
| Admin scenario | Configuration, signed restart, drain, replay rejection and reload checklist |
| Turkish/English UI | Playwright verifies locale switch, translated privacy text and document language |
| Privacy | Recording-provider test proves preview rows, identifiers and unapproved fields are absent from the LLM request |
| Execution | Deterministic worker, Spark report and Spark ML tests cover lifecycle through result artifacts |
| SSE recovery | Frontend test proves event-ID deduplication and authoritative REST reload before reconnect |
| Public packaging | Public README is concise; private `analysis/` material is ignored by default |

## Executed acceptance gate

Command:

```bash
./scripts/demo-acceptance.sh
```

Observed results:

- dataset volume verification: passed;
- static infrastructure and shell validation: passed;
- Maven build: passed;
- Java JUnit/Testcontainers: 34 passed;
- Python Ruff: passed;
- Python pytest including Spark: 36 passed;
- Svelte diagnostics: 0 errors, 0 warnings;
- frontend component tests: 2 passed;
- frontend production build: passed;
- Chromium end-to-end tests: 2 passed;
- overall acceptance script: passed.

## Security assertions

- No raw business rows are sent to an LLM.
- No secrets are embedded in generated data, scripts, scenarios or documentation.
- The browser continues to communicate only with Java.
- Python has no PostgreSQL, Keycloak or Docker control dependency.
- Sales ingestion remains notification-driven.
- Admin restart remains signed, audience-bound, short-lived and replay-protected.

## Non-blocking observations

- `npm audit` reports five dependency findings: one low, one moderate, two high
  and one critical. Updating them safely requires a focused dependency review.
- The production frontend build reports an ECharts-related JavaScript chunk
  above 500 kB. Functional acceptance is unaffected; future optimization can
  use route-level dynamic imports.
- Generated CSVs are intentionally ignored and reproduced locally to avoid
  adding approximately 84 MiB of deterministic data to source control.
