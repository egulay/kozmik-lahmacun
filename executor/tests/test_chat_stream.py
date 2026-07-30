import json
from uuid import uuid4

from fastapi.testclient import TestClient

from kozmik_executor.chat.api import _messages
from kozmik_executor.main import app
from kozmik_executor.chat.models import ChatStreamRequest


def request_body(content: str) -> dict[str, object]:
    return {
        "schemaVersion": "1.0",
        "requestId": str(uuid4()),
        "threadId": str(uuid4()),
        "assistantMessageId": str(uuid4()),
        "actorUserId": str(uuid4()),
        "correlationId": "python-chat-test",
        "language": "en",
        "capabilities": ["REPORTER"],
        "history": [{"role": "user", "content": content}],
    }


def events(response_text: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in response_text.splitlines()]


def test_chat_prompt_requires_latest_message_language(deterministic_effective_configuration) -> None:
    request = ChatStreamRequest.model_validate(request_body("Merhaba"))

    system_prompt = _messages(request, deterministic_effective_configuration.llm)[0]["content"]

    assert "latest user message" in system_prompt
    assert "Turkish" in system_prompt
    assert "English for every other language" in system_prompt


def test_streams_deterministic_completion(monkeypatch) -> None:
    monkeypatch.setenv("INTERNAL_API_KEY", "test-internal-key")

    response = TestClient(app).post(
        "/internal/v1/chat/stream",
        headers={"X-Internal-API-Key": "test-internal-key"},
        json=request_body("hello"),
    )
    streamed = events(response.text)

    assert response.status_code == 200
    assert streamed[0]["type"] == "message-started"
    assert streamed[-1]["type"] == "message-completed"
    assert streamed[-1]["content"] == "Mock response: hello"
    assert all(event["schemaVersion"] == "1.0" for event in streamed)


def test_streams_sanitized_failure(monkeypatch) -> None:
    monkeypatch.setenv("INTERNAL_API_KEY", "test-internal-key")

    response = TestClient(app).post(
        "/internal/v1/chat/stream",
        headers={"X-Internal-API-Key": "test-internal-key"},
        json=request_body("[fail]"),
    )
    streamed = events(response.text)

    assert streamed[-1]["type"] == "message-failed"
    assert streamed[-1]["errorCode"] == "MOCK_PROVIDER_FAILURE"
    assert "content" not in streamed[-1] or streamed[-1]["content"] is None


def test_rejects_missing_internal_authentication(monkeypatch) -> None:
    monkeypatch.setenv("INTERNAL_API_KEY", "test-internal-key")

    response = TestClient(app).post("/internal/v1/chat/stream", json=request_body("hello"))

    assert response.status_code == 401


def test_rejects_unbounded_history(monkeypatch) -> None:
    monkeypatch.setenv("INTERNAL_API_KEY", "test-internal-key")
    body = request_body("hello")
    body["history"] = [{"role": "user", "content": "x"}] * 21

    response = TestClient(app).post(
        "/internal/v1/chat/stream",
        headers={"X-Internal-API-Key": "test-internal-key"},
        json=body,
    )

    assert response.status_code == 422
