import json
import logging
import os
import re
import secrets
import unicodedata
from collections.abc import AsyncIterator
from functools import lru_cache
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from lingua import Language, LanguageDetectorBuilder

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
_ENGLISH_WORDS = frozenset({
    "a", "an", "and", "are", "can", "do", "for", "how", "i", "in", "is", "it",
    "like", "me", "of", "the", "this", "to", "understood", "what", "who", "you",
    "your",
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
    words = set(re.findall(r"[^\W\d_]+", latest.casefold(), flags=re.UNICODE))
    english_score = len(words.intersection(_ENGLISH_WORDS))
    turkish_score = len(words.intersection(_TURKISH_WORDS))
    # A Turkish proper noun such as “Türkiye” must not switch an otherwise English
    # sentence to Turkish. Sentence-level function words are stronger evidence than
    # a diacritic in one name.
    if english_score >= 2 and english_score > turkish_score:
        return "English"
    if any(character in _TURKISH_CHARACTERS for character in latest):
        return "Turkish"
    is_turkish = bool(words.intersection(_TURKISH_STRONG_WORDS)) or (
        turkish_score >= 2
    )
    return "Turkish" if is_turkish else "English"


def _business_limitations_answer(response_language: str) -> str:
    if response_language == "Turkish":
        return (
            "Sistemde bulunan verilerden raporlar, karşılaştırmalar, grafikler, tahminler "
            "ve karar odaklı özetler hazırlayabilirim.\n\n"
            "Şunları yapamam:\n"
            "- Sohbete yapıştırılan veya henüz sisteme aktarılmamış verileri analiz edemem.\n"
            "- Tahminlerin kesin olarak gerçekleşeceğini garanti edemem; sonuçlar mevcut "
            "geçmiş verilerdeki örüntülere dayanan yaklaşık değerlerdir.\n"
            "- Hesaplanmış bir senaryo karşılaştırması olmadan fiyat, indirim, miktar veya "
            "politika değişikliği öneremem. Bu tür kararlar kontrollü bir iş denemesiyle "
            "doğrulanmalıdır."
        )
    return (
        "I can prepare reports, comparisons, charts, predictions, and decision-oriented "
        "summaries from data available in the system.\n\n"
        "What I cannot do:\n"
        "- I cannot analyze data pasted into the conversation or information that has not "
        "yet been added to the system.\n"
        "- I cannot guarantee that predictions will happen exactly as estimated; they are "
        "approximate results based on patterns in the available historical data.\n"
        "- I cannot recommend changing prices, discounts, quantities, or policies without a "
        "calculated scenario comparison. Such decisions should be validated with a controlled "
        "business test."
    )


def _creator_answer(response_language: str) -> str:
    if response_language == "Turkish":
        return (
            "Kozmik Lahmacun, yazılım mimarı ve veri platformu mühendisi Emre Gülay "
            "tarafından tasarlanmış ve geliştirilmiştir."
        )
    return (
        "Kozmik Lahmacun was designed and developed by Emre Gülay, a software architect "
        "and data platform engineer."
    )


def _capability_answer(response_language: str) -> str:
    return (
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


def _special_chat_response(latest_message: str) -> str | None:
    normalized = unicodedata.normalize("NFKD", latest_message.casefold())
    normalized = "".join(
        character for character in normalized if not unicodedata.combining(character)
    ).replace("ı", "i")
    if re.search(
        r"\b(?:limitations?|cannot do|can't do|what not to expect|"
        r"sinirlamalar\w*|neleri yapamaz\w*|ne beklememeli\w*)\b",
        normalized,
    ):
        return "limitations"
    if re.search(
        r"\b(?:who (?:created|built|designed|developed|engineered)|creator|designer|"
        r"seni kim|kim (?:yapti|gelistirdi|tasarladi)|yaraticin|muhendisin)\b",
        normalized,
    ):
        return "creator"
    if re.search(
        r"\b(?:who are you|what are you|what do you do|what can you do|functionality|"
        r"what is your (?:job|purpose|role)|describe yourself|how can you help|kimsin|nesin|"
        r"ne (?:is|gorev) yap\w*|neler yapabil\w*|nasil yardimci ol\w*|"
        r"ne oldugunu soyle\w*|ne is yaptig\w*|yaptig\w* is|"
        r"(?:isin|gorevin|amacin|islevin) (?:ne|nedir)|kendini tanit\w*|"
        r"seni .{0,40} tanit\w*)\b",
        normalized,
    ):
        return "capability"
    return None


def _supported_chat_history(history):
    retained = []
    retain_assistant = True
    for message in history:
        if message.role.value == "user":
            language_code = _detected_language_code(message.content)
            retain_assistant = language_code in (None, "en", "tr")
            if retain_assistant:
                retained.append(message)
        elif retain_assistant:
            retained.append(message)
    return retained


def _messages(
    request: ChatStreamRequest, config: EffectiveLlmConfiguration
) -> list[dict[str, str]]:
    if len(request.history) > config.max_context_messages:
        raise ProviderError("CHAT_CONTEXT_LIMIT_EXCEEDED")
    if sum(len(message.content) for message in request.history) > config.max_context_characters:
        raise ProviderError("CHAT_CONTEXT_LIMIT_EXCEEDED")
    response_language = _response_language(request)
    latest_message = next(
        (message.content for message in reversed(request.history) if message.role.value == "user"),
        "",
    )
    special_response = _special_chat_response(latest_message)
    limitations_answer = _business_limitations_answer(response_language)
    creator_answer = _creator_answer(response_language)
    capability_answer = _capability_answer(response_language)
    system = (
        "You are a governed analytics assistant. Answer conversationally. "
        "Never request, infer, or reproduce raw business rows. Never output executable code, "
        "SQL, or an execution plan. Use only the bounded conversation supplied. "
        f"The mandatory response language for this turn is {response_language}. Use only "
        f"{response_language}. Determine the current response from the latest user message, not "
        "from earlier user or assistant messages. Do not introduce or explain your identity, "
        "capabilities, creator, or limitations unless the latest user message explicitly asks "
        "for that information."
    )
    if special_response == "capability":
        system += (
            " The latest message explicitly asks about identity or capabilities. Return this "
            "localized capability answer exactly, preserving its paragraphs and bullet points, "
            f"with no additional text:\n\n{capability_answer}"
        )
    elif special_response == "limitations":
        system += (
            " The latest message explicitly asks about limitations. Return this localized "
            "limitations answer exactly, preserving its paragraphs and bullet points, with no "
            f"additional text:\n\n{limitations_answer}"
        )
    elif special_response == "creator":
        system += (
            " The latest message explicitly asks who created the platform. Return this localized "
            f"creator answer exactly, with no additional text:\n\n{creator_answer}"
        )
    return [{"role": "system", "content": system}] + [
        {"role": message.role.value, "content": message.content}
        for message in _supported_chat_history(request.history)
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
        latest_message = next(
            (message.content for message in reversed(request.history)
             if message.role.value == "user"),
            "",
        )
        special_response = _special_chat_response(latest_message)
        if special_response is not None:
            response_language = _response_language(request)
            content = {
                "capability": _capability_answer(response_language),
                "limitations": _business_limitations_answer(response_language),
                "creator": _creator_answer(response_language),
            }[special_response]
            yield _line(ChatStreamEvent(
                type=StreamEventType.DELTA, delta=content, **base
            ))
            yield _line(ChatStreamEvent(
                type=StreamEventType.COMPLETED, content=content, **base
            ))
            return
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
        f"description={entity.description or ''}; columns={','.join(entity.column_names)}; "
        f"columnLabels={','.join(entity.column_labels)}"
        for entity in request.entities
    )
    return (
        "First detect the language of the current request itself. Only English and Turkish "
        "are supported. Return UNSUPPORTED_LANGUAGE for every other language, regardless of "
        "whether the request otherwise resembles conversation, reporting, or prediction. "
        "Classify supported-language intent only. REPORT means descriptive analysis of existing "
        "data: totals, averages, counts, grouping, filtering, comparisons, trends, unusual "
        "observed patterns, or charts. ML requires an explicit request to predict or estimate "
        "an unknown outcome, forecast, train a model, classify, score probability or risk, or "
        "perform machine learning. Controlled what-if or counterfactual scenarios that change "
        "input values and compare predicted outcomes with an unchanged baseline are ML, "
        "including equivalent Turkish requests using kontrollü senaryo and değişmemiş başlangıç. "
        "Charts and unusual-pattern descriptions alone are REPORT. Do not generate a plan, SQL, "
        "code, or request raw rows.\n"
        f"Capabilities: {','.join(request.capabilities)}\n"
        f"Schema metadata only:\n{metadata}\n"
        f"Bounded conversation:\n{history}\n"
        f"Current request:\n{request.user_request}"
    )


async def _unsupported_language_response(
    provider, user_request: str, detected_language_code: str | None = None,
) -> str:
    if re.search(r"[\u0600-\u06ff]", user_request):
        return (
            "الطلبات المتعلقة بالتواصل والتحليل مدعومة فقط باللغة الإنجليزية أو التركية. "
            "يرجى إعادة صياغة الطلب باللغة الإنجليزية أو التركية."
        )
    normalized = user_request.casefold()
    localized = (
        (
            ("hola", "español", "informe"),
            "La comunicación y las solicitudes de análisis solo están disponibles en inglés "
            "o turco. Repita su solicitud en inglés o turco.",
        ),
        (
            ("bonjour", "français", "rapport"),
            "La communication et les demandes d’analyse sont disponibles uniquement en anglais "
            "ou en turc. Veuillez reformuler votre demande dans l’une de ces langues.",
        ),
        (
            ("hallo", "deutsch", "bericht"),
            "Kommunikation und Analyseanfragen werden nur auf Englisch oder Türkisch unterstützt. "
            "Bitte formulieren Sie Ihre Anfrage auf Englisch oder Türkisch neu.",
        ),
        (
            ("ciao", "italiano"),
            "La comunicazione e le richieste di analisi sono supportate solo in inglese o turco. "
            "Ripeti la richiesta in inglese o turco.",
        ),
    )
    for markers, response in localized:
        if any(marker in normalized for marker in markers):
            return response
    try:
        language_code = detected_language_code
        if language_code is None:
            detected = await provider.complete_json(
                "Identify only the language of the supplied message. Return exactly one JSON "
                "object with its BCP-47 language code in 'languageCode'. Do not translate, quote, "
                "summarize, or answer the message.",
                json.dumps({"userMessage": user_request}, ensure_ascii=False),
            )
            language_code = detected.get("languageCode")
        if not isinstance(language_code, str) or not re.fullmatch(
            r"[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", language_code
        ):
            raise ValueError("provider returned an invalid language code")
        translated = await provider.complete_json(
            "Translate only the supplied fixed policy into the specified BCP-47 language. "
            "Return exactly one JSON object with the translation in 'message'. Do not add an "
            "introduction, quote, example, explanation, or any other text.",
            json.dumps({
                "languageCode": language_code,
                "fixedPolicy": (
                    "Requests related to communication and analysis are supported only in "
                    "English or Turkish. Please rephrase your request in English or Turkish."
                ),
            }, ensure_ascii=False),
        )
        response = translated.get("message")
        if (
            isinstance(response, str)
            and 1 <= len(response.strip()) <= 2_000
            and not _repeats_user_request(user_request, response)
        ):
            return response.strip()
    except (ProviderError, ValueError, TypeError, AttributeError):
        logger.warning("unsupported_language_translation_failed")
    return (
        "Requests related to communication and analysis are supported only in English or "
        "Turkish. Please rephrase your request in English or Turkish."
    )


def _repeats_user_request(user_request: str, response: str) -> bool:
    source_words = re.findall(r"[^\W\d_]+", user_request.casefold(), flags=re.UNICODE)
    response_words = re.findall(r"[^\W\d_]+", response.casefold(), flags=re.UNICODE)
    if len(source_words) < 3:
        return False
    source_phrases = {
        tuple(source_words[offset:offset + 3])
        for offset in range(len(source_words) - 2)
    }
    return any(
        tuple(response_words[offset:offset + 3]) in source_phrases
        for offset in range(len(response_words) - 2)
    )


def _governed_intent_override(
    request: ClassificationRequest, provider_intent: IntentType,
) -> IntentType:
    """Correct clear descriptive-report requests without guessing ambiguous intent."""
    if provider_intent == IntentType.UNSUPPORTED_LANGUAGE:
        return provider_intent
    text = request.user_request.lower()
    scenario_signal = re.search(
        r"\b(?:scenarios?|options?|alternatives?|senaryo\w*|secenek\w*|seçenek\w*|alternatif\w*)\b",
        text,
        re.IGNORECASE,
    )
    decision_signal = re.search(
        r"\b(?:recommend\w*|recommendation|should\s+(?:we|management)|decision|"
        r"öner\w*|oner\w*|öneri\w*|oneri\w*|karar\w*|değiştirmeli\w*|degistirmeli\w*)\b",
        text,
        re.IGNORECASE,
    )
    change_signal = re.search(
        r"\b(?:change|adjust|increase|decrease|policy|price|discount|quantity|rate|"
        r"değiş\w*|degis\w*|artır\w*|artir\w*|azalt\w*|politika\w*|fiyat\w*|"
        r"indirim\w*|miktar\w*|oran\w*)\b",
        text,
        re.IGNORECASE,
    )
    if scenario_signal and decision_signal and change_signal:
        return IntentType.ML
    explicit_ml = re.search(
        r"\b(?:predict(?:ion)?|forecast|train(?:ing)?|machine learning|"
        r"classif(?:y|ication)|probability|risk score|anomaly model|"
        r"likely\s+to|predictions?\s+preview|compare\s+suitable\s+(?:prediction\s+)?methods|"
        r"estimate(?:d)?\s+(?:expected|future)|"
        r"what[- ]if|counterfactual|controlled\s+scenarios?|unchanged\s+baseline|"
        r"tahmin\w*|öngör\w*|model\s+eğit\w*|sınıflandır\w*|olasılık|risk\s+puan\w*|"
        r"kontrollü\s+senaryo\w*|değişmemiş\s+başlangıç|muhtemel|olası)\b",
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


def _clear_governed_intent(request: ClassificationRequest) -> IntentType | None:
    resolved = _governed_intent_override(request, IntentType.CONVERSATIONAL)
    return resolved if resolved != IntentType.CONVERSATIONAL else None


def _uses_unsupported_script(value: str) -> bool:
    # English and Turkish use Latin script. A non-Latin writing system can therefore be
    # rejected deterministically before asking a provider to classify business intent.
    return bool(re.search(
        r"[\u0370-\u03ff\u0400-\u052f\u0590-\u05ff\u0600-\u06ff"
        r"\u0900-\u097f\u0e00-\u0e7f\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]",
        value,
    ))


@lru_cache(maxsize=1)
def _language_detector():
    return LanguageDetectorBuilder.from_all_spoken_languages().build()


def _detected_language_code(value: str) -> str | None:
    words = re.findall(r"[^\W\d_]+", value.casefold(), flags=re.UNICODE)
    if any(character in _TURKISH_CHARACTERS for character in value) or set(words).intersection(
        _TURKISH_STRONG_WORDS
    ):
        return "tr"
    values = _language_detector().compute_language_confidence_values(value)
    if not values:
        return None
    strongest = values[0]
    code = strongest.language.iso_code_639_1
    language_code = code.name.casefold() if code is not None else None
    if strongest.language in (Language.ENGLISH, Language.TURKISH):
        return language_code
    if _uses_unsupported_script(value):
        return language_code
    second = values[1].value if len(values) > 1 else 0.0
    relative_confidence = strongest.value / max(second, 0.000_001)
    contains_foreign_diacritic = any(
        character.isalpha() and ord(character) > 127
        and character not in _TURKISH_CHARACTERS
        for character in value
    )
    if relative_confidence >= 1.2 and (
        contains_foreign_diacritic or (len(words) >= 4 and strongest.value >= 0.2)
    ):
        return language_code
    return None


def _enforce_supported_language_detection(
    detected_language_code: str | None, provider_intent: IntentType,
) -> IntentType:
    if (
        detected_language_code in ("en", "tr")
        and provider_intent == IntentType.UNSUPPORTED_LANGUAGE
    ):
        logger.warning(
            "provider_language_misclassification correctedLanguage=%s",
            detected_language_code,
        )
        return IntentType.CONVERSATIONAL
    return provider_intent


def _normalized_terms(value: str) -> set[str]:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    normalized = "".join(character for character in normalized
                         if not unicodedata.combining(character))
    ignored = {
        "and", "bir", "data", "entity", "record", "records", "veri", "verilerinde",
        "kaydı", "kaydi", "detayı", "detayi", "the", "using", "kullanarak", "ile",
        "icin", "için", "ve",
    }
    return {
        term for term in re.findall(r"[^\W\d_]+", normalized, flags=re.UNICODE)
        if len(term) >= 3 and term not in ignored
    }


def _deterministic_entity_resolution(request: ClassificationRequest) -> UUID | None:
    request_terms = _normalized_terms(request.user_request)
    if not request_terms:
        return None
    ranked: list[tuple[int, int, int, UUID]] = []
    for entity in request.entities:
        # An explicit entity-name reference is stronger than incidental prose shared by
        # generated descriptions (for example Turkish articles such as "bir"). Keeping
        # the scores separate also avoids delaying an otherwise obvious request behind
        # the serialized local-LLM structured-planning queue.
        name_score = len(request_terms.intersection(_normalized_terms(entity.name)))
        description_score = len(request_terms.intersection(
            _normalized_terms(entity.description or "")
        ))
        column_score = len(request_terms.intersection(_normalized_terms(
            " ".join([*entity.column_names, *entity.column_labels])
        )))
        if name_score or column_score or description_score:
            ranked.append((name_score, column_score, description_score, entity.entity_id))
    ranked.sort(reverse=True, key=lambda item: (item[0], item[1], item[2]))
    if not ranked or (
        len(ranked) > 1 and ranked[0][:3] == ranked[1][:3]
    ):
        return None
    return ranked[0][3]


async def _resolve_entity(
    provider, request: ClassificationRequest, intent: IntentType,
) -> UUID | None:
    if intent in (IntentType.CONVERSATIONAL, IntentType.UNSUPPORTED_LANGUAGE) \
            or not request.entities:
        return None
    deterministic = _deterministic_entity_resolution(request)
    if deterministic is not None:
        return deterministic
    authorized = {
        str(entity.entity_id): {
            "entityId": str(entity.entity_id),
            "name": entity.name,
            "description": entity.description,
            "columnNames": entity.column_names,
            "columnLabels": entity.column_labels,
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
        # Non-Latin languages are rejected deterministically. The provider checks Latin-script
        # requests so languages such as Spanish, French, German, and Italian are also gated.
        detected_language_code = _detected_language_code(request.user_request)
        if (
            detected_language_code in (None, "en", "tr")
            and _special_chat_response(request.user_request) is not None
        ):
            intent = IntentType.CONVERSATIONAL
        elif detected_language_code not in (None, "en", "tr"):
            intent = IntentType.UNSUPPORTED_LANGUAGE
        else:
            intent = _enforce_supported_language_detection(
                detected_language_code,
                await provider.classify(_classification_prompt(request)),
            )
        intent = _governed_intent_override(request, intent)
        selected_entity_id = await _resolve_entity(provider, request, intent)
        unsupported_language_response = (
            await _unsupported_language_response(
                provider, request.user_request, detected_language_code
            )
            if intent == IntentType.UNSUPPORTED_LANGUAGE
            else None
        )
        return ClassificationResponse(
            request_id=request.request_id,
            correlation_id=request.correlation_id,
            intent=intent,
            selected_entity_id=selected_entity_id,
            provider=provider.name,
            model=provider.model,
            unsupported_language_response=unsupported_language_response,
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
