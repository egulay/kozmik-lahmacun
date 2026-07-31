import json
from uuid import uuid4

from fastapi.testclient import TestClient

from kozmik_executor.chat.api import _messages, _response_language
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

    assert "mandatory response language for this turn is Turkish" in system_prompt
    assert "latest user message" in system_prompt


def test_chat_language_is_determined_from_latest_message_not_ui_language(
    deterministic_effective_configuration,
) -> None:
    english = ChatStreamRequest.model_validate({
        **request_body("What are you?"),
        "language": "tr",
        "history": [
            {"role": "user", "content": "Daha önce Türkçe konuştuk."},
            {"role": "assistant", "content": "Elbette."},
            {"role": "user", "content": "What are you?"},
        ],
    })
    turkish = ChatStreamRequest.model_validate({
        **request_body("Ne iş yaparsın?"),
        "language": "en",
    })

    assert _response_language(english) == "English"
    assert _response_language(turkish) == "Turkish"
    english_prompt = _messages(
        english, deterministic_effective_configuration.llm
    )[0]["content"]
    assert "mandatory response language for this turn is English" in english_prompt


def test_chat_prompt_explains_capabilities_in_business_language(
    deterministic_effective_configuration,
) -> None:
    request = ChatStreamRequest.model_validate(request_body("What can you do?"))

    system_prompt = _messages(request, deterministic_effective_configuration.llm)[0]["content"]

    assert "return the following localized capability answer exactly" in system_prompt
    assert "I am an AI assistant designed to help business users" in system_prompt
    assert "Once your data is available in the system" in system_prompt
    assert "Example requests:" in system_prompt
    assert "- Compare performance across regions." in system_prompt
    assert "İş kullanıcılarının" not in system_prompt

    turkish_request = ChatStreamRequest.model_validate(
        request_body("Neler yapabilirsin ve bana nasıl yardımcı olursun?")
    )
    turkish_prompt = _messages(
        turkish_request, deterministic_effective_configuration.llm
    )[0]["content"]
    assert "mandatory response language for this turn is Turkish" in turkish_prompt
    assert (
        "Şirket verilerinizi raporlara, karşılaştırmalara ve anlaşılır öngörülere dönüştüren"
        in turkish_prompt
    )
    assert "Verileriniz sisteme aktarıldıktan sonra" in turkish_prompt
    assert "Örnek istekler:" in turkish_prompt
    assert "- Aylık değişimi bir grafikle göster." in turkish_prompt
    assert "I am an AI assistant" not in turkish_prompt


def test_chat_prompt_treats_identity_questions_as_capability_questions(
    deterministic_effective_configuration,
) -> None:
    for content in (
        "Who are you?",
        "What are you?",
        "Sen kimsin?",
        "Sen nesin?",
        "Ne iş yaparsın?",
        "Neler yapabilirsin?",
        "Bana nasıl yardımcı olursun?",
    ):
        request = ChatStreamRequest.model_validate(request_body(content))
        system_prompt = _messages(
            request, deterministic_effective_configuration.llm
        )[0]["content"]

        assert "who or what you are" in system_prompt
        assert "equivalent identity or capability question" in system_prompt
        assert "localized capability answer exactly" in system_prompt


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
