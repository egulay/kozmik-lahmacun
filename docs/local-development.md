# Local development

## Configuration and secrets

All Compose settings come from `.env`. Run `scripts/setup-env.sh` once to copy
`.env.example` and replace secret placeholders with cryptographically random
local values. `.env` is ignored by Git. Production deployments must use their
own secret injection mechanism; the generated values are development-only.

The LLM provider is configured with `LLM_PROVIDER`, `LLM_BASE_URL`, and
`LLM_MODEL`. Local development defaults to LM Studio. Start its Local Server
and load the configured model before `start-all.sh`. For an OpenAI-compatible
provider, also set `OPENAI_COMPATIBLE_API_KEY`. The executor refuses to start
when the configured endpoint or model is unavailable or when a required key is
missing.

SMTP configuration uses `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM`,
`SMTP_FROM_DISPLAY_NAME`, `SMTP_AUTH`, `SMTP_STARTTLS`, `SMTP_SSL`,
`SMTP_USERNAME`, and `SMTP_PASSWORD`. The local defaults target Mailpit without
authentication. Startup writes the complete configuration to Vault and resolves
Keycloak's runtime SMTP environment back from Vault before Keycloak starts.
Java receives the equivalent `spring.mail.*` properties from its Vault context.
Production credentials should be supplied only through the protected
`KOZMIK_SECRETS_FILE`; they must not be added to `.env` or realm JSON.

## Deterministic lifecycle

- `scripts/dev-up.sh` validates configuration, pulls/starts services, waits for
  health, and requires both initialization jobs to finish successfully.
- `scripts/smoke-test.sh` verifies PostgreSQL, Redis, Kafka topics, MinIO buckets
  and event notification, and the Keycloak realm/client/roles.
- `scripts/dev-down.sh` stops the project without deleting data.
- `scripts/dev-down.sh --volumes` also deletes this project's named volumes.
- `scripts/stop-all.sh` stops the local Java, Python, and frontend processes and
  removes the complete demo Docker stack, including its named volumes.

The Compose project name is fixed through `.env`, preventing accidental
interaction with unrelated stacks.

## Application logs

Java and Python write the same messages to their console and to daily UTF-8 log
files. Local defaults are:

- `logs/java/yyyy-MM/yyyy-MM-dd.log`
- `logs/python/yyyy-MM/yyyy-MM-dd.log`

Set `JAVA_LOG_DIR` or `PYTHON_LOG_DIR` in `.env` to change the roots. Relative
paths are resolved from the repository root by the local startup scripts.
`LOG_LEVEL` controls Java and `PYTHON_LOG_LEVEL` controls Python. Java retention
is configurable with `LOG_MAX_HISTORY_DAYS` and `LOG_TOTAL_SIZE_CAP`. The
monthly directories are created automatically.

PostgreSQL uses separate `kozmik` application and `keycloak` identity
databases. This keeps Flyway ownership isolated from Keycloak's internal
schema.

## Initialized resources

Kafka topics:

- `execution.commands.v1`
- `execution.events.v1`
- `execution.results.v1`
- `ingestion.events.v1`
- `ingestion.records.v1`
- `ingestion.stream.status.v1`

MinIO buckets:

- `raw`
- `refined`
- `reports`
- `models`
- `results`

Object-created events from the `raw` bucket are sent to
`ingestion.events.v1`. Keycloak imports the `kozmik` realm, the three platform
roles, and the confidential `kozmik-backend` OIDC client. No local users are
committed; create them in the Keycloak admin console and assign realm roles.

## Service shell checks

```bash
./scripts/test-all.sh
```

The command runs Maven tests, Python tests/lint, frontend checks/tests, and
static infrastructure validation. It does not start application services.

After infrastructure is running, start the Java foundation with:

```bash
./scripts/backend-dev.sh
```

The helper maps the generated local credentials into Spring configuration and
disables the Secure cookie flag only for local HTTP. Production defaults keep
the session cookie Secure.
