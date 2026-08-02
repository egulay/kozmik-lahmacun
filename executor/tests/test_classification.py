import asyncio
import json
from uuid import uuid4

from fastapi.testclient import TestClient

from kozmik_executor.chat.api import (
    _business_limitations_answer,
    _creator_answer,
    _clear_governed_intent,
    _detected_language_code,
    _enforce_supported_language_detection,
    _deterministic_entity_resolution,
    _governed_intent_override,
    _repeats_user_request,
    _unsupported_language_response,
)
from kozmik_executor.chat.models import ClassificationRequest, IntentType
from kozmik_executor.main import app


def body(request: str) -> dict[str, object]:
    return {
        "schemaVersion": "1.0",
        "requestId": str(uuid4()),
        "correlationId": "classification-test",
        "actorUserId": str(uuid4()),
        "language": "en",
        "capabilities": ["REPORTER"],
        "userRequest": request,
        "history": [],
        "entities": [
            {
                "entityId": str(uuid4()),
                "name": "Orders",
                "columnNames": ["region", "net_amount"],
            }
        ],
    }


def classify(monkeypatch, request: str):
    monkeypatch.setenv("INTERNAL_API_KEY", "test-internal-key")
    return TestClient(app).post(
        "/internal/v1/chat/classify",
        headers={"X-Internal-API-Key": "test-internal-key"},
        json=body(request),
    )


def test_classifies_conversational_report_and_ml(monkeypatch) -> None:
    assert classify(monkeypatch, "Hello there").json()["intent"] == "CONVERSATIONAL"
    assert classify(monkeypatch, "Create a report with sum by region").json()["intent"] == "REPORT"
    assert classify(monkeypatch, "Forecast next month sales").json()["intent"] == "ML"


def test_foreign_language_execution_request_is_rejected_before_planning(monkeypatch) -> None:
    response = classify(monkeypatch, "Hola, crea un informe de ventas por región")

    assert response.status_code == 200
    assert response.json()["intent"] == "UNSUPPORTED_LANGUAGE"
    assert response.json()["selectedEntityId"] is None
    assert "solo están disponibles en inglés o turco" in (
        response.json()["unsupportedLanguageResponse"]
    )


def test_arabic_request_gets_controlled_arabic_language_guidance(monkeypatch) -> None:
    response = classify(monkeypatch, "هكذا هي الأمور، أها أها، لقد أعجبني ذلك")

    assert response.status_code == 200
    assert response.json()["intent"] == "UNSUPPORTED_LANGUAGE"
    assert response.json()["unsupportedLanguageResponse"] == (
        "الطلبات المتعلقة بالتواصل والتحليل مدعومة فقط باللغة الإنجليزية أو التركية. "
        "يرجى إعادة صياغة الطلب باللغة الإنجليزية أو التركية."
    )


def test_generic_foreign_translation_never_receives_original_message() -> None:
    original = "Nii see on, aha aha, mulle meeldis see"

    class Provider:
        def __init__(self):
            self.prompts = []

        async def complete_json(self, _system_prompt, user_prompt):
            self.prompts.append(user_prompt)
            if len(self.prompts) == 1:
                return {"languageCode": "et"}
            return {
                "message": (
                    "Suhtluse ja analüüsiga seotud päringuid toetatakse ainult inglise või "
                    "türgi keeles. Palun sõnastage päring inglise või türgi keeles."
                )
            }

    provider = Provider()
    response = asyncio.run(_unsupported_language_response(provider, original))

    assert json.loads(provider.prompts[0])["userMessage"] == original
    assert "userMessage" not in json.loads(provider.prompts[1])
    assert original not in provider.prompts[1]
    assert not _repeats_user_request(original, response)
    assert response.startswith("Suhtluse ja analüüsiga seotud päringuid")


def test_repeated_user_phrase_is_detected() -> None:
    assert _repeats_user_request(
        "Nii see on, aha aha, mulle meeldis see",
        "See on, aha aha, mulle meeldis see. Suhtlemine on piiratud.",
    )


def test_deterministic_detector_separates_supported_and_foreign_latin_languages() -> None:
    assert _detected_language_code("É assim que eu gosto.") == "pt"
    assert _detected_language_code("Nii see on, aha aha, mulle meeldis see") == "et"
    assert _detected_language_code("What are you?") == "en"
    assert _detected_language_code("Satış raporu oluştur") == "tr"
    assert _detected_language_code("Tamam anladım kusura bakma. Naber?") == "tr"
    assert _detected_language_code("tamam anladım. bak Türkçe yazıyorum nasılsın?") == "tr"
    # Very short ambiguous messages must not be falsely blocked.
    assert _detected_language_code("Hi") is None
    assert _detected_language_code("test") is None


def test_portuguese_never_reaches_normal_conversation(monkeypatch) -> None:
    response = classify(monkeypatch, "É assim que eu gosto.")

    assert response.status_code == 200
    assert response.json()["intent"] == "UNSUPPORTED_LANGUAGE"
    assert response.json()["selectedEntityId"] is None
    assert response.json()["unsupportedLanguageResponse"] == (
        "Solicitações relacionadas à comunicação e análise são suportadas apenas em inglês "
        "ou turco. Reformule sua solicitação em inglês ou turco."
    )
    assert "AI assistant" not in response.json()["unsupportedLanguageResponse"]


def test_supported_language_detection_overrides_provider_language_error() -> None:
    assert _enforce_supported_language_detection(
        "tr", IntentType.UNSUPPORTED_LANGUAGE
    ) == IntentType.CONVERSATIONAL
    assert _enforce_supported_language_detection(
        "en", IntentType.UNSUPPORTED_LANGUAGE
    ) == IntentType.CONVERSATIONAL
    assert _enforce_supported_language_detection(
        "pt", IntentType.UNSUPPORTED_LANGUAGE
    ) == IntentType.UNSUPPORTED_LANGUAGE


def test_turkish_capability_variants_are_always_conversational(monkeypatch) -> None:
    for request in (
        "Seni anneme tanıtıyorum. ne iş yaptığını söyler misin?",
        "Yaptığın iş nedir?",
    ):
        response = classify(monkeypatch, request)

        assert response.status_code == 200
        assert response.json()["intent"] == "CONVERSATIONAL"
        assert response.json()["selectedEntityId"] is None


def test_business_limitations_answer_is_localized_and_nontechnical() -> None:
    english = _business_limitations_answer("English")
    turkish = _business_limitations_answer("Turkish")

    assert "What I cannot do:" in english
    assert "Şunları yapamam:" in turkish
    assert "controlled business test" in english
    assert "kontrollü bir iş denemesi" in turkish
    for technical_term in ("Spark", "Kafka", "SQL", "JSON"):
        assert technical_term not in english
        assert technical_term not in turkish


def test_creator_answer_is_localized() -> None:
    english = _creator_answer("English")
    turkish = _creator_answer("Turkish")

    assert english == (
        "Kozmik Lahmacun was designed and developed by Emre Gülay, a software architect "
        "and data platform engineer."
    )
    assert turkish == (
        "Kozmik Lahmacun, yazılım mimarı ve veri platformu mühendisi Emre Gülay "
        "tarafından tasarlanmış ve geliştirilmiştir."
    )


def test_descriptive_aggregations_and_charts_override_erroneous_ml_classification() -> None:
    payload = body(
        "Analyze call activity by month and region. Show total call count, average duration, "
        "compare call types, identify unusual observed patterns, and include a pie chart."
    )
    request = ClassificationRequest.model_validate(payload)

    assert _governed_intent_override(request, IntentType.ML) == IntentType.REPORT


def test_explicit_prediction_is_not_overridden_by_report_words() -> None:
    payload = body(
        "Predict expected call charge and show an actual-versus-predicted chart."
    )
    request = ClassificationRequest.model_validate(payload)

    assert _governed_intent_override(request, IntentType.REPORT) == IntentType.ML


def test_likely_threshold_prediction_with_charts_is_ml() -> None:
    payload = body(
        "Identify which calls are likely to last longer than five minutes based on call "
        "type and region. Compare suitable methods automatically, include a predictions "
        "preview and charts."
    )
    request = ClassificationRequest.model_validate(payload)

    assert _governed_intent_override(request, IntentType.REPORT) == IntentType.ML


def test_turkish_controlled_what_if_request_is_ml() -> None:
    payload = body(
        "Satış verilerinde birim fiyat, miktar ve indirim oranını ayrı ayrı %5 artırıp "
        "azaltan kontrollü senaryoları test et. Her senaryoyu değişmemiş başlangıç "
        "değeriyle karşılaştır ve yalnızca hesaplanan kanıta dayanarak yönetime koşullu "
        "bir öneri sun."
    )
    payload["language"] = "tr"
    request = ClassificationRequest.model_validate(payload)

    assert _governed_intent_override(request, IntentType.REPORT) == IntentType.ML


def test_plain_business_turkish_policy_scenario_request_is_ml() -> None:
    payload = body(
        "İndirim politikasını değiştirmeli miyiz? Uygun senaryoları karşılaştır ve öneri sun."
    )
    payload["language"] = "tr"
    request = ClassificationRequest.model_validate(payload)

    assert _governed_intent_override(
        request, IntentType.CONVERSATIONAL
    ) == IntentType.ML


def test_plain_business_english_policy_scenario_request_is_ml() -> None:
    request = ClassificationRequest.model_validate(body(
        "Should we change the pricing policy? Compare suitable scenarios and recommend an option."
    ))

    assert _governed_intent_override(
        request, IntentType.CONVERSATIONAL
    ) == IntentType.ML


def test_english_controlled_what_if_request_is_ml() -> None:
    payload = body(
        "Run controlled scenarios changing price by plus and minus five percent, compare "
        "predicted outcomes with the unchanged baseline, and recommend the strongest option."
    )
    request = ClassificationRequest.model_validate(payload)

    assert _governed_intent_override(request, IntentType.REPORT) == IntentType.ML


def test_clear_turkish_what_if_intent_does_not_require_provider_classification() -> None:
    payload = body(
        "Satış verilerinde kontrollü senaryoları değişmemiş başlangıç değeriyle karşılaştır."
    )
    payload["language"] = "tr"

    assert _clear_governed_intent(
        ClassificationRequest.model_validate(payload)
    ) == IntentType.ML


def test_explicit_entity_name_is_resolved_without_provider_call() -> None:
    payload = body("Satış verilerinde aylık toplamları karşılaştır ve grafik göster")
    sales_id = str(uuid4())
    payload["language"] = "tr"
    payload["entities"] = [
        {
            "entityId": sales_id,
            "name": "Satış Kaydı",
            "description": "Satış işlemleri",
            "columnNames": ["net_amount"],
        },
        {
            "entityId": str(uuid4()),
            "name": "Çağrı Detayı Kaydı",
            "description": "Telekom çağrı kullanımı",
            "columnNames": ["duration_seconds"],
        },
    ]

    assert str(_deterministic_entity_resolution(
        ClassificationRequest.model_validate(payload)
    )) == sales_id


def test_explicit_entity_name_wins_over_incidental_description_word() -> None:
    payload = body(
        "Satış verilerinde birim fiyat, miktar ve indirim oranını ayrı ayrı %5 artırıp "
        "azaltan kontrollü senaryoları test et. Her senaryoyu değişmemiş başlangıç "
        "değeriyle karşılaştır."
    )
    sales_id = str(uuid4())
    payload["language"] = "tr"
    payload["entities"] = [
        {
            "entityId": sales_id,
            "name": "Satış Kaydı",
            "description": "Ürün detayları ve fiyatlandırma içeren bir satış kaydı",
            "columnNames": ["net_amount"],
        },
        {
            "entityId": str(uuid4()),
            "name": "Çağrı Detayı Kaydı",
            "description": "Bir telefon görüşmesi hakkında detaylı bilgiler",
            "columnNames": ["duration_seconds"],
        },
    ]

    assert str(_deterministic_entity_resolution(
        ClassificationRequest.model_validate(payload)
    )) == sales_id


def test_localized_column_labels_resolve_entity_after_unrelated_chat() -> None:
    payload = body(
        "İndirim politikasını değiştirmeli miyiz? Uygun senaryoları karşılaştır ve öneri sun."
    )
    sales_id = str(uuid4())
    payload["language"] = "tr"
    payload["history"] = [
        {"role": "user", "content": "Beethoven kimdir?"},
        {"role": "assistant", "content": "Ludwig van Beethoven bir bestecidir."},
    ]
    payload["entities"] = [
        {
            "entityId": sales_id,
            "name": "Satış Kaydı",
            "description": "Satış işlemleri",
            "columnNames": ["region", "discount_rate", "net_amount"],
            "columnLabels": ["Bölge", "İndirim oranı", "Net satış tutarı"],
        },
        {
            "entityId": str(uuid4()),
            "name": "Çağrı Detayı Kaydı",
            "description": "Telekom çağrı kayıtları",
            "columnNames": ["call_type", "duration_seconds"],
            "columnLabels": ["Çağrı türü", "Görüşme süresi"],
        },
    ]

    request = ClassificationRequest.model_validate(payload)

    assert str(_deterministic_entity_resolution(request)) == sales_id


def test_ambiguous_entity_terms_still_defer_to_provider() -> None:
    payload = body("Bölgesel sonuçları karşılaştır")
    payload["entities"] = [
        {
            "entityId": str(uuid4()), "name": "Regional Sales",
            "description": "Regional performance", "columnNames": ["region"],
        },
        {
            "entityId": str(uuid4()), "name": "Regional Calls",
            "description": "Regional performance", "columnNames": ["region"],
        },
    ]

    assert _deterministic_entity_resolution(
        ClassificationRequest.model_validate(payload)
    ) is None


def test_contract_rejects_raw_row_payload(monkeypatch) -> None:
    payload = body("Create a report")
    payload["rawRows"] = [{"customer": "secret"}]
    monkeypatch.setenv("INTERNAL_API_KEY", "test-internal-key")

    response = TestClient(app).post(
        "/internal/v1/chat/classify",
        headers={"X-Internal-API-Key": "test-internal-key"},
        json=payload,
    )

    assert response.status_code == 422


def test_classification_reduces_stream_history_to_latest_ten_messages() -> None:
    payload = body("Surprise me")
    payload["history"] = [
        {"role": "user", "content": f"message-{index}"} for index in range(20)
    ]

    request = ClassificationRequest.model_validate(payload)

    assert len(request.history) == 10
    assert request.history[0].content == "message-10"
    assert request.history[-1].content == "message-19"


def test_reporter_can_be_classified_as_ml_without_authorizing_execution(monkeypatch) -> None:
    response = classify(monkeypatch, "Build a prediction model")

    assert response.status_code == 200
    assert response.json()["intent"] == "ML"
    assert "plan" not in response.json()


def test_semantically_selects_sales_entity_from_turkish_report_request(monkeypatch) -> None:
    payload = body("Bölge bazlı toplam satış raporu oluştur")
    sales_id = str(uuid4())
    payload["language"] = "tr"
    payload["entities"] = [
        {
            "entityId": sales_id,
            "name": "Satış Kaydı",
            "description": "Bölge ve ürün bazında satış işlemleri",
            "columnNames": ["region", "net_amount", "quantity"],
        },
        {
            "entityId": str(uuid4()),
            "name": "Çağrı Detayı Kaydı",
            "description": "Telekom çağrı kullanım kayıtları",
            "columnNames": ["caller", "duration_seconds"],
        },
    ]
    monkeypatch.setenv("INTERNAL_API_KEY", "test-internal-key")

    response = TestClient(app).post(
        "/internal/v1/chat/classify",
        headers={"X-Internal-API-Key": "test-internal-key"},
        json=payload,
    )

    assert response.status_code == 200
    assert response.json()["intent"] == "REPORT"
    assert response.json()["selectedEntityId"] == sales_id
