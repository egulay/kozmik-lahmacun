# Chat streaming contract

Java owns chat threads, messages, ownership checks, retention metadata, and
terminal state. Python owns provider streaming only and has no PostgreSQL or
Keycloak dependency.

Browser flow:

1. Create a thread with `POST /api/chat/threads`.
2. Post content to `POST /api/chat/threads/{threadId}/messages`.
3. Connect to
   `GET /api/chat/threads/{threadId}/stream?assistantMessageId={messageId}`.
4. Reload `GET /api/chat/threads/{threadId}/messages` after reconnect; REST is
   authoritative.

SSE event names are `message-started`, `message-delta`,
`message-completed`, and `message-failed`. IDs are based on the durable
assistant-message UUID and a monotonic stream index. A reconnect after terminal
completion receives a terminal event reconstructed from PostgreSQL.

Java calls `POST /internal/v1/chat/stream` with `X-Internal-API-Key`. The
versioned request contains correlation, actor, thread, assistant-message,
language, role-capability, and bounded-history fields. Python responds as
newline-delimited JSON events. The history is limited to 20 messages and 12,000
characters; individual messages are limited to 20,000 characters.

The current Python provider is deterministic and intended for tests. LM Studio
and OpenAI-compatible provider classes are interface shells only; real provider
network calls and execution planning are deferred.
