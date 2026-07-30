from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(word.capitalize() for word in rest)


class ContractModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class EffectiveLlmConfiguration(ContractModel):
    provider: str
    base_url: str
    model: str
    timeout_seconds: int = Field(ge=1, le=300)
    max_retries: int = Field(ge=0, le=5)
    max_context_messages: int = Field(ge=1, le=50)
    max_context_characters: int = Field(ge=100, le=50_000)


class EffectiveConfiguration(ContractModel):
    schema_version: str = Field(pattern=r"^1\.0$")
    llm: EffectiveLlmConfiguration
    execution: dict[str, object] | None = None


class ChatRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class HistoryMessage(ContractModel):
    role: ChatRole
    content: str = Field(min_length=1, max_length=20_000)


class ChatStreamRequest(ContractModel):
    schema_version: str = Field(pattern=r"^1\.0$")
    request_id: UUID
    thread_id: UUID
    assistant_message_id: UUID
    actor_user_id: UUID
    correlation_id: str = Field(min_length=1, max_length=100)
    language: str = Field(pattern=r"^[a-z]{2}(-[A-Z]{2})?$")
    capabilities: list[str] = Field(max_length=3)
    history: list[HistoryMessage] = Field(max_length=20)

    @model_validator(mode="after")
    def bounded_history_characters(self) -> "ChatStreamRequest":
        if sum(len(message.content) for message in self.history) > 12_000:
            raise ValueError("history exceeds character bound")
        return self


class StreamEventType(StrEnum):
    STARTED = "message-started"
    DELTA = "message-delta"
    COMPLETED = "message-completed"
    FAILED = "message-failed"


class ChatStreamEvent(ContractModel):
    schema_version: str = "1.0"
    event_id: UUID = Field(default_factory=uuid4)
    correlation_id: str
    assistant_message_id: UUID
    type: StreamEventType
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    delta: str | None = None
    content: str | None = None
    provider: str | None = None
    model: str | None = None
    error_code: str | None = None


class IntentType(StrEnum):
    CONVERSATIONAL = "CONVERSATIONAL"
    REPORT = "REPORT"
    ML = "ML"


class EntityMetadata(ContractModel):
    entity_id: UUID
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    column_names: list[str] = Field(max_length=500)


class ClassificationRequest(ContractModel):
    schema_version: str = Field(pattern=r"^1\.0$")
    request_id: UUID
    correlation_id: str = Field(min_length=1, max_length=100)
    actor_user_id: UUID
    language: str = Field(pattern=r"^[a-z]{2}(-[A-Z]{2})?$")
    capabilities: list[str] = Field(max_length=3)
    user_request: str = Field(min_length=1, max_length=4_000)
    history: list[HistoryMessage] = Field(max_length=10)
    entities: list[EntityMetadata] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def bounded_input(self) -> "ClassificationRequest":
        total = len(self.user_request) + sum(len(message.content) for message in self.history)
        if total > 8_000:
            raise ValueError("classification context exceeds character bound")
        return self


class ClassificationResponse(ContractModel):
    schema_version: str = "1.0"
    request_id: UUID
    correlation_id: str
    intent: IntentType
    selected_entity_id: UUID | None = None
    provider: str
    model: str
