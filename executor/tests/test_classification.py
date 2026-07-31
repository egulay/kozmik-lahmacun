from uuid import uuid4

from fastapi.testclient import TestClient

from kozmik_executor.chat.api import (
    _clear_governed_intent,
    _deterministic_entity_resolution,
    _governed_intent_override,
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
