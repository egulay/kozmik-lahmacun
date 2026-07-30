from uuid import uuid4

from fastapi.testclient import TestClient

from kozmik_executor.chat.models import ClassificationRequest
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
