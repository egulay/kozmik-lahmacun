# Lifecycle hardening

## Cancellation and timeout

Java records `cancel_requested_at`, appends an audit/status record, and publishes
a versioned `CANCEL` command to `execution.control.v1`. Python consumes control
commands independently from execution commands, sets the cooperative
cancellation event, and calls Spark `cancelJobGroup(executionId)`.

Both services enforce terminal-state consistency. Once an execution is
`SUCCEEDED`, `FAILED`, `CANCELLED`, or `TIMED_OUT`, later conflicting status
events cannot replace that outcome. Java also scans durable `timeout_at` values
and sends cancellation when an execution is overdue.

## Retention

The Java retention schedule reads the independent platform settings:

- `retention.chat_days`
- `retention.execution_days`
- `retention.preview_days`
- `retention.artifact_days`

Expired chat threads are physically deleted and PostgreSQL cascades that deletion
to their wholly owned messages. Result previews are redacted. MinIO objects are
removed before their references are marked deleted. Object-deletion
failures remain retryable through `deletion_error_code`; each retention run
produces a durable, payload-free audit event.

## Controlled executor restart

Only an authenticated Admin can call `/api/admin/executor/restart`. Java
persists the request and sends a short-lived HMAC-SHA256 command containing a
command ID, audience, operation, expiry, nonce, and drain timeout. Python:

1. validates the internal API key, signature, audience, operation, and expiry;
2. atomically claims the nonce in its persistent SQLite replay ledger;
3. stops accepting new execution work;
4. drains active work, then cooperatively cancels it after the configured limit;
5. exits with code `75`.

The optional Compose `application` profile runs the executor with
`restart: on-failure` and a persistent replay/event ledger volume. A fresh
executor process loads effective configuration from Java during application
startup before it reports healthy.

Python never accesses Docker or Keycloak. Docker observes only the process exit
code and applies its restart policy.
