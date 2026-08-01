from fastapi.testclient import TestClient

from kozmik_executor.main import app


def test_internal_health_is_available(monkeypatch) -> None:
    monkeypatch.setenv("INTERNAL_API_KEY", "test-internal-key")
    response = TestClient(app).get(
        "/internal/v1/health", headers={"X-Internal-API-Key": "test-internal-key"}
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "AVAILABLE",
        "providerStatus": "AVAILABLE",
        "provider": "deterministic-mock",
        "model": "mock-v1",
        "errorCode": None,
    }
