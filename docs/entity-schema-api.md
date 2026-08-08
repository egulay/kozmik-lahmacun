# Data Entity Structure API

All responses use message-contract `schemaVersion` `1.0`. This field versions
the HTTP document shape; it is not a data-entity schema version.

- `GET /api/entities` lists active Data Entities to every authenticated user.
- `GET /api/entities/{entityId}/schema` returns the entity's registered structure.
- `GET /api/entities/{entityId}/schema/columns` returns its paged columns.
- `/api/admin/entities/**` provides Admin-only entity create/update operations.

An entity UUID is the immutable identity of one data structure. If incoming data
has a different structure it must use a new entity UUID. The platform does not
maintain entity schema versions, column classifications, nullability rules,
per-column eligibility switches, or per-user entity grants.

Python never connects to PostgreSQL. It retrieves the registered structure from:

`GET /internal/v1/entities/{entityId}/schema?actorUserId={applicationUserUuid}&capability=REPORTER|SCIENTIST`

The request requires `X-Internal-API-Key`. Java validates the actor and enforces
operation capability: authenticated users can report; SCIENTIST and ADMIN can
run ML. Browser sessions and provider tokens are never accepted by or returned
from this endpoint.

Errors use a stable body containing `schemaVersion`, `code`, a sanitized
`message`, `correlationId`, `timestamp`, and optional `fieldErrors`.
