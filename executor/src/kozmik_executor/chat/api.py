import json
import logging
import os
import secrets
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse

from .configuration import JavaConfigurationClient
from .models import (
    ChatStreamEvent,
    ChatStreamRequest,
    ClassificationRequest,
    ClassificationResponse,
    EffectiveLlmConfiguration,
    IntentType,
    StreamEventType,
)
from .providers import ProviderError, ProviderRegistry

router = APIRouter(prefix="/internal/v1/chat")
configuration_client = JavaConfigurationClient()
provider_registry = ProviderRegistry()
logger = logging.getLogger(__name__)


def _line(event: ChatStreamEvent) -> str:
    return json.dumps(event.model_dump(by_alias=True, mode="json"), separators=(",", ":")) + "\n"


def _authenticate(supplied: str | None) -> None:
    expected = os.environ.get("INTERNAL_API_KEY", "")
    if not expected or supplied is None or not secrets.compare_digest(expected, supplied):
        raise HTTPException(status_code=401, detail="internal authentication required")


def _messages(
    request: ChatStreamRequest, config: EffectiveLlmConfiguration
) -> list[dict[str, str]]:
    if len(request.history) > config.max_context_messages:
        raise ProviderError("CHAT_CONTEXT_LIMIT_EXCEEDED")
    if sum(len(message.content) for message in request.history) > config.max_context_characters:
        raise ProviderError("CHAT_CONTEXT_LIMIT_EXCEEDED")
    system = (
        "You are a governed analytics assistant. Answer conversationally. "
        "Never request, infer, or reproduce raw business rows. Never output executable code, "
        "SQL, or an execution plan. Use only the bounded conversation supplied. "
        "Determine the response language only from the latest user message: respond in Turkish "
        "when that message is Turkish, respond in English when it is English, and respond in "
        "English for every other language. Do not let earlier messages determine the language."
    )
    return [{"role": "system", "content": system}] + [
        {"role": message.role.value, "content": message.content} for message in request.history
    ]


async def _events(request: ChatStreamRequest) -> AsyncIterator[str]:
    base: dict[str, object] = {
        "correlation_id": request.correlation_id,
        "assistant_message_id": request.assistant_message_id,
    }
    chunks: list[str] = []
    try:
        effective = await configuration_client.load()
        provider = provider_registry.resolve(effective.llm)
        base.update(provider=provider.name, model=provider.model)
        yield _line(ChatStreamEvent(type=StreamEventType.STARTED, **base))
        async for chunk in provider.stream(_messages(request, effective.llm)):
            chunks.append(chunk)
            yield _line(ChatStreamEvent(type=StreamEventType.DELTA, delta=chunk, **base))
        yield _line(
            ChatStreamEvent(type=StreamEventType.COMPLETED, content="".join(chunks), **base)
        )
    except ProviderError as exception:
        logger.warning(
            "chat_stream_failed code=%s retryable=%s",
            exception.code, exception.retryable,
        )
        yield _line(
            ChatStreamEvent(
                type=StreamEventType.FAILED,
                error_code=exception.code,
                **base,
            )
        )
    except Exception:
        logger.exception("chat_stream_failed code=CHAT_STREAM_FAILED")
        yield _line(
            ChatStreamEvent(
                type=StreamEventType.FAILED,
                error_code="CHAT_STREAM_FAILED",
                **base,
            )
        )


@router.post("/stream", response_class=StreamingResponse)
def stream_chat(
    request: ChatStreamRequest,
    x_internal_api_key: str | None = Header(default=None),
) -> StreamingResponse:
    _authenticate(x_internal_api_key)
    return StreamingResponse(_events(request), media_type="application/x-ndjson")


def _classification_prompt(request: ClassificationRequest) -> str:
    history = "\n".join(
        f"{message.role.value}: {message.content}" for message in request.history
    )
    metadata = "\n".join(
        f"entityId={entity.entity_id}; name={entity.name}; "
        f"description={entity.description or ''}; columns={','.join(entity.column_names)}"
        for entity in request.entities
    )
    return (
        "Classify intent only. Do not generate a plan, SQL, code, or request raw rows.\n"
        f"Capabilities: {','.join(request.capabilities)}\n"
        f"Schema metadata only:\n{metadata}\n"
        f"Bounded conversation:\n{history}\n"
        f"Current request:\n{request.user_request}"
    )


async def _resolve_entity(
    provider, request: ClassificationRequest, intent: IntentType,
) -> UUID | None:
    if intent == IntentType.CONVERSATIONAL or not request.entities:
        return None
    authorized = {
        str(entity.entity_id): {
            "entityId": str(entity.entity_id),
            "name": entity.name,
            "description": entity.description,
            "columnNames": entity.column_names,
        }
        for entity in request.entities
    }
    prompt = (
        "ENTITY_RESOLUTION_REQUEST="
        + json.dumps({
            "currentRequest": request.user_request,
            "conversation": [
                message.model_dump(mode="json") for message in request.history[-6:]
            ],
            "authorizedEntities": list(authorized.values()),
        }, ensure_ascii=False, separators=(",", ":"))
    )
    try:
        decision = await provider.complete_json(
            "Select the single authorized data entity that semantically fits the current "
            "report or ML request. Use names, descriptions, columns, and bounded conversation. "
            "Return only {\"selectedEntityId\":\"<authorized UUID>\"}. Return "
            "{\"selectedEntityId\":null} only when genuinely ambiguous. Never invent an ID.",
            prompt,
        )
        selected = decision.get("selectedEntityId")
        return UUID(selected) if isinstance(selected, str) and selected in authorized else None
    except (ProviderError, ValueError, TypeError, AttributeError):
        return None


@router.post("/classify", response_model=ClassificationResponse)
async def classify(
    request: ClassificationRequest,
    x_internal_api_key: str | None = Header(default=None),
) -> ClassificationResponse:
    _authenticate(x_internal_api_key)
    try:
        effective = await configuration_client.load()
        provider = provider_registry.resolve(effective.llm)
        intent = await provider.classify(_classification_prompt(request))
        selected_entity_id = await _resolve_entity(provider, request, intent)
        return ClassificationResponse(
            request_id=request.request_id,
            correlation_id=request.correlation_id,
            intent=intent,
            selected_entity_id=selected_entity_id,
            provider=provider.name,
            model=provider.model,
        )
    except ProviderError as exception:
        raise HTTPException(
            status_code=503 if exception.retryable else 422,
            detail={
                "schemaVersion": "1.0",
                "code": exception.code,
                "retryable": exception.retryable,
            },
        ) from exception
