import json
import logging
import os
import re
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

_TURKISH_CHARACTERS = frozenset("çğıöşüÇĞİÖŞÜ")
_TURKISH_WORDS = frozenset({
    "ben", "bana", "beni", "biz", "bu", "bir", "değil", "icin", "için", "ile",
    "kim", "kimsin", "mı", "mi", "mu", "mü", "nasıl", "ne", "neden", "neler",
    "nedir", "nesin", "oluştur", "rapor", "sen", "satış", "tahmin", "yap",
    "yaparsın", "yardımcı",
})
_TURKISH_STRONG_WORDS = frozenset({
    "kimsin", "merhaba", "nasıl", "nedir", "neler", "nesin", "oluştur", "satış",
    "tahmin", "yaparsın", "yardımcı",
})


def _line(event: ChatStreamEvent) -> str:
    return json.dumps(event.model_dump(by_alias=True, mode="json"), separators=(",", ":")) + "\n"


def _authenticate(supplied: str | None) -> None:
    expected = os.environ.get("INTERNAL_API_KEY", "")
    if not expected or supplied is None or not secrets.compare_digest(expected, supplied):
        raise HTTPException(status_code=401, detail="internal authentication required")


def _response_language(request: ChatStreamRequest) -> str:
    latest = next(
        (message.content for message in reversed(request.history) if message.role.value == "user"),
        "",
    )
    if any(character in _TURKISH_CHARACTERS for character in latest):
        return "Turkish"
    words = set(re.findall(r"[^\W\d_]+", latest.casefold(), flags=re.UNICODE))
    is_turkish = bool(words.intersection(_TURKISH_STRONG_WORDS)) or (
        len(words.intersection(_TURKISH_WORDS)) >= 2
    )
    return "Turkish" if is_turkish else "English"


def _messages(
    request: ChatStreamRequest, config: EffectiveLlmConfiguration
) -> list[dict[str, str]]:
    if len(request.history) > config.max_context_messages:
        raise ProviderError("CHAT_CONTEXT_LIMIT_EXCEEDED")
    if sum(len(message.content) for message in request.history) > config.max_context_characters:
        raise ProviderError("CHAT_CONTEXT_LIMIT_EXCEEDED")
    response_language = _response_language(request)
    capability_answer = (
        "Şirket verilerinizi raporlara, karşılaştırmalara ve anlaşılır öngörülere dönüştüren "
        "bir yapay zekâ asistanıyım. Verileriniz sisteme aktarıldıktan sonra raporlar "
        "hazırlayabilir, toplamları hesaplayabilir, farklı "
        "dönemleri veya grupları karşılaştırabilir, eğilimleri grafiklerle gösterebilir ve "
        "sonuçları anlaşılır bir dille özetleyebilirim. Ayrıca mevcut verilere dayanarak "
        "geleceğe yönelik tahminler hazırlayabilirim; bu tahminler kesin sonuçlar değil, "
        "karar vermeyi destekleyen veriye dayalı öngörülerdir.\n\n"
        "Örnek istekler:\n"
        "- Bölgeler arasındaki performansı karşılaştır.\n"
        "- Aylık değişimi bir grafikle göster.\n"
        "- Mevcut verilere göre gelecek dönemdeki sonucu tahmin et."
        if response_language == "Turkish"
        else
        "I am an AI assistant designed to help business users understand their company data "
        "and make informed decisions. Once your data is available in the system, I can prepare "
        "reports, calculate totals, compare periods or groups, show trends with charts, and "
        "summarize results in plain business language. I can also prepare predictions based on "
        "the available data; these are data-based estimates rather than guaranteed outcomes.\n\n"
        "Example requests:\n"
        "- Compare performance across regions.\n"
        "- Show the monthly change with a chart.\n"
        "- Estimate the next period's outcome based on available data."
    )
    system = (
        "You are a governed analytics assistant. Answer conversationally. "
        "Never request, infer, or reproduce raw business rows. Never output executable code, "
        "SQL, or an execution plan. Use only the bounded conversation supplied. "
        f"The mandatory response language for this turn is {response_language}. Use only "
        f"{response_language} throughout the response. This language was determined from the "
        "latest user message; never use the UI language or earlier messages instead. "
        "When the user asks who or what you are, what you do, what the platform can do, how you "
        "can help, or asks an equivalent identity or capability question, answer for a "
        "nontechnical business user. This includes Turkish expressions "
        "such as 'Sen kimsin?', 'Sen nesin?', 'Ne iş yaparsın?', 'Neler yapabilirsin?' and "
        "'Bana nasıl yardımcı olursun?'. For every identity or capability question, return the "
        "following localized capability answer exactly, preserving its paragraph, heading and "
        f"three bullet points, with no additional text:\n\n{capability_answer}"
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
        "Classify intent only. REPORT means descriptive analysis of existing data: totals, "
        "averages, counts, grouping, filtering, comparisons, trends, unusual observed patterns, "
        "or charts. ML requires an explicit request to predict or estimate an unknown outcome, "
        "forecast, train a model, classify, score probability or risk, or perform machine "
        "learning. Controlled what-if or counterfactual scenarios that change input values and "
        "compare predicted outcomes with an unchanged baseline are ML, including equivalent "
        "Turkish requests using kontrollü senaryo and değişmemiş başlangıç. Charts and "
        "unusual-pattern descriptions alone are REPORT. Do not generate "
        "a plan, SQL, code, or request raw rows.\n"
        f"Capabilities: {','.join(request.capabilities)}\n"
        f"Schema metadata only:\n{metadata}\n"
        f"Bounded conversation:\n{history}\n"
        f"Current request:\n{request.user_request}"
    )


def _governed_intent_override(
    request: ClassificationRequest, provider_intent: IntentType,
) -> IntentType:
    """Correct clear descriptive-report requests without guessing ambiguous intent."""
    text = request.user_request.lower()
    explicit_ml = re.search(
        r"\b(?:predict(?:ion)?|forecast|train(?:ing)?|machine learning|"
        r"classif(?:y|ication)|probability|risk score|anomaly model|"
        r"estimate(?:d)?\s+(?:expected|future)|"
        r"what[- ]if|counterfactual|controlled\s+scenarios?|unchanged\s+baseline|"
        r"tahmin\w*|öngör\w*|model\s+eğit\w*|sınıflandır\w*|olasılık|risk\s+puan\w*|"
        r"kontrollü\s+senaryo\w*|değişmemiş\s+başlangıç)\b",
        text,
        re.IGNORECASE,
    )
    if explicit_ml:
        return IntentType.ML
    report_signals = re.findall(
        r"\b(?:report|analy[sz]e|analysis|show|list|total|sum|average|count|"
        r"group(?:ed)?|compare|comparison|trend|chart|graph|pie|bar|line|"
        r"breakdown|busiest|highest|lowest|most|least|"
        r"rapor|analiz|göster\w*|listele\w*|toplam|ortalama|sayı|adet|"
        r"grupla\w*|karşılaştır\w*|eğilim|grafik|dağılım|en\s+(?:yüksek|düşük|yoğun))\b",
        text,
        re.IGNORECASE,
    )
    return IntentType.REPORT if len(report_signals) >= 2 else provider_intent


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
        intent = _governed_intent_override(request, intent)
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
