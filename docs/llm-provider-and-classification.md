# LLM provider and classification contract

Java owns effective provider configuration. Python loads:

`GET /internal/v1/config/effective`

using `X-Internal-API-Key`. The versioned response contains provider name, base
URL, model, timeouts, retry count, and context bounds. It never contains API
keys, browser sessions, or provider tokens.

`LM_STUDIO` is the default provider. `OPENAI_COMPATIBLE` is the alternative.
Both use the OpenAI-compatible `/chat/completions` streaming protocol and
`/models` health endpoint. OpenAI-compatible credentials are injected into
Python as `OPENAI_COMPATIBLE_API_KEY`; they are not persisted in normal platform
settings or returned by Java.

Executor startup is fail-fast: the configured `/models` endpoint must be
reachable and must advertise the exact configured `LLM_MODEL`. When
`OPENAI_COMPATIBLE` is selected, `OPENAI_COMPATIBLE_API_KEY` must also be
present. Provider, base URL, and model are configured in the repository `.env`.
The deterministic mock provider is restricted to automated tests.

Python exposes authenticated internal endpoints:

- `POST /internal/v1/chat/stream`
- `POST /internal/v1/chat/classify`
- `GET /internal/v1/health`

Classification returns one of `CONVERSATIONAL`, `REPORT`, or `ML`. It does not
create an execution order and does not grant permission to execute that intent.
Inputs accept bounded conversation, capabilities, and entity/column names only.
Unknown fields—including raw-row payloads—are rejected.

Provider calls use configurable total timeouts and bounded exponential retries.
Streaming calls retry only before emitting the first chunk, preventing duplicate
partial output. Errors expose stable codes and retryability without leaking
provider response bodies, secrets, or prompt content.
