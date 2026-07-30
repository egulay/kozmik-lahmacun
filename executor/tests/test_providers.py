import json

import httpx
import pytest

from kozmik_executor.chat.models import EffectiveLlmConfiguration, IntentType
from kozmik_executor.chat.providers import (
    LmStudioProvider,
    OpenAiCompatibleProvider,
    ProviderError,
    ProviderRegistry,
)


def config(provider: str) -> EffectiveLlmConfiguration:
    return EffectiveLlmConfiguration(
        provider=provider,
        base_url="http://provider.test/v1",
        model="test-model",
        timeout_seconds=5,
        max_retries=2,
        max_context_messages=20,
        max_context_characters=12_000,
    )


def test_lm_studio_is_default_provider_shape() -> None:
    provider = ProviderRegistry().resolve(config("LM_STUDIO"))

    assert isinstance(provider, LmStudioProvider)
    assert provider.name == "lm-studio"


def test_openai_compatible_provider_is_alternative(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "runtime-secret")

    provider = ProviderRegistry().resolve(config("OPENAI_COMPATIBLE"))

    assert isinstance(provider, OpenAiCompatibleProvider)
    assert provider.name == "openai-compatible"
    assert provider.api_key == "runtime-secret"


@pytest.mark.anyio
async def test_retry_policy_recovers_from_transient_network_errors() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise httpx.ConnectError("temporary", request=request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps({"intent": "REPORT"})}}
                ]
            },
        )

    provider = OpenAiCompatibleProvider(
        config("OPENAI_COMPATIBLE"), transport=httpx.MockTransport(handler)
    )

    assert await provider.classify("report") == IntentType.REPORT
    assert attempts == 3


@pytest.mark.anyio
async def test_classification_accepts_lm_studio_markdown_json_without_response_format() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert "response_format" not in payload
        return httpx.Response(
            200,
            json={"choices": [{"message": {
                "content": '```json\n{"intent":"CONVERSATIONAL"}\n```'
            }}]},
        )

    provider = LmStudioProvider(
        config("LM_STUDIO"), transport=httpx.MockTransport(handler)
    )

    assert await provider.classify("hello") == IntentType.CONVERSATIONAL


@pytest.mark.anyio
async def test_lm_studio_structured_completion_accepts_fenced_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert "response_format" not in payload
        return httpx.Response(
            200,
            json={"choices": [{"message": {
                "content": 'Here is the order:\n```json\n{"executionType":"REPORT"}\n```'
            }}]},
        )

    provider = LmStudioProvider(
        config("LM_STUDIO"), transport=httpx.MockTransport(handler)
    )

    assert await provider.complete_json("system", "request") == {
        "executionType": "REPORT"
    }


@pytest.mark.anyio
async def test_retry_exhaustion_returns_typed_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    provider = OpenAiCompatibleProvider(
        config("OPENAI_COMPATIBLE"), transport=httpx.MockTransport(handler)
    )

    with pytest.raises(Exception) as captured:
        await provider.classify("report")

    assert getattr(captured.value, "code") == "LLM_PROVIDER_TIMEOUT"
    assert getattr(captured.value, "retryable") is True


@pytest.mark.anyio
async def test_lm_studio_streams_openai_compatible_chunks() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        return httpx.Response(
            200,
            text=(
                'data: {"choices":[{"delta":{"content":"hello "}}]}\n\n'
                'data: {"choices":[{"delta":{"content":"world"}}]}\n\n'
                "data: [DONE]\n\n"
            ),
            headers={"content-type": "text/event-stream"},
        )

    provider = LmStudioProvider(config("LM_STUDIO"), transport=httpx.MockTransport(handler))

    chunks = [
        chunk
        async for chunk in provider.stream(
            [{"role": "user", "content": "bounded prompt"}]
        )
    ]

    assert chunks == ["hello ", "world"]


@pytest.mark.anyio
async def test_provider_health_uses_models_endpoint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/models"
        return httpx.Response(200, json={"data": [{"id": "test-model"}]})

    provider = LmStudioProvider(config("LM_STUDIO"), transport=httpx.MockTransport(handler))

    assert await provider.health() is True


@pytest.mark.anyio
async def test_provider_health_rejects_missing_configured_model() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"id": "another-model"}]})

    provider = LmStudioProvider(config("LM_STUDIO"), transport=httpx.MockTransport(handler))

    with pytest.raises(ProviderError) as captured:
        await provider.ensure_ready()

    assert captured.value.code == "LLM_MODEL_NOT_AVAILABLE"
    assert "test-model" in str(captured.value)
    assert "another-model" in str(captured.value)


@pytest.mark.anyio
async def test_provider_readiness_explains_unreachable_endpoint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    provider = LmStudioProvider(config("LM_STUDIO"), transport=httpx.MockTransport(handler))

    with pytest.raises(ProviderError) as captured:
        await provider.ensure_ready()

    assert captured.value.code == "LLM_PROVIDER_UNAVAILABLE"
    assert "start its Local Server" in str(captured.value)
    assert "LLM_PROVIDER=OPENAI_COMPATIBLE" in str(captured.value)


def test_openai_compatible_requires_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_COMPATIBLE_API_KEY", raising=False)

    with pytest.raises(ProviderError) as captured:
        ProviderRegistry().resolve(config("OPENAI_COMPATIBLE"))

    assert captured.value.code == "LLM_API_KEY_MISSING"
    assert "OPENAI_COMPATIBLE_API_KEY" in str(captured.value)
