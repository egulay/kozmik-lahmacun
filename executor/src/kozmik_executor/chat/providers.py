import asyncio
import json
import os
import re
from collections.abc import AsyncIterator
from typing import Protocol

import httpx

from .models import EffectiveLlmConfiguration, IntentType


def _parse_intent(content: str) -> IntentType:
    candidate = content.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate, flags=re.IGNORECASE)
        candidate = re.sub(r"\s*```$", "", candidate)
    try:
        value = json.loads(candidate)
        if isinstance(value, dict):
            return IntentType(value["intent"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        pass

    structured_matches = set(re.findall(
        r'["\']intent["\']\s*:\s*["\'](CONVERSATIONAL|REPORT|ML)["\']',
        candidate,
        flags=re.IGNORECASE,
    ))
    if len(structured_matches) == 1:
        return IntentType(structured_matches.pop().upper())

    matches = set(re.findall(r"\b(CONVERSATIONAL|REPORT|ML)\b", candidate.upper()))
    if len(matches) == 1:
        return IntentType(matches.pop())
    raise ValueError("provider did not return exactly one supported intent")


def _parse_json_object(content: str) -> dict:
    candidate = content.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate, flags=re.IGNORECASE)
        candidate = re.sub(r"\s*```$", "", candidate)
    try:
        value = json.loads(candidate)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for offset, character in enumerate(candidate):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(candidate[offset:])
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            continue
    raise ValueError("provider did not return a JSON object")


class ProviderError(RuntimeError):
    def __init__(
        self, code: str, retryable: bool = False, message: str | None = None
    ) -> None:
        super().__init__(message or code)
        self.code = code
        self.retryable = retryable


class ChatProvider(Protocol):
    name: str
    model: str

    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]: ...
    async def classify(self, prompt: str) -> IntentType: ...
    async def complete_json(self, system_prompt: str, user_prompt: str) -> dict: ...
    async def health(self) -> bool: ...


class OpenAiCompatibleProvider:
    name = "openai-compatible"

    def __init__(
        self,
        config: EffectiveLlmConfiguration,
        api_key: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config
        self.model = config.model
        self.api_key = api_key
        self.transport = transport

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        payload = {"model": self.model, "messages": messages, "stream": True, "temperature": 0}
        emitted = False
        for attempt in range(self.config.max_retries + 1):
            try:
                timeout = httpx.Timeout(self.config.timeout_seconds)
                async with httpx.AsyncClient(
                    timeout=timeout, headers=self._headers(), transport=self.transport
                ) as client:
                    async with client.stream(
                        "POST", f"{self.config.base_url.rstrip('/')}/chat/completions", json=payload
                    ) as response:
                        response.raise_for_status()
                        async for line in response.aiter_lines():
                            if not line.startswith("data:"):
                                continue
                            data = line[5:].strip()
                            if data == "[DONE]":
                                return
                            chunk = json.loads(data)
                            content = chunk.get("choices", [{}])[0].get("delta", {}).get("content")
                            if content:
                                emitted = True
                                yield content
                        return
            except (httpx.TimeoutException, httpx.NetworkError) as exception:
                if emitted or attempt >= self.config.max_retries:
                    raise ProviderError("LLM_PROVIDER_TIMEOUT", retryable=True) from exception
                await asyncio.sleep(0.05 * (2**attempt))
            except (httpx.HTTPStatusError, json.JSONDecodeError, KeyError) as exception:
                raise ProviderError("LLM_PROVIDER_INVALID_RESPONSE") from exception

    async def classify(self, prompt: str) -> IntentType:
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Return exactly one JSON object with intent equal to "
                        "CONVERSATIONAL, REPORT, or ML. Do not generate SQL, code, or a plan."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "temperature": 0,
        }
        for attempt in range(self.config.max_retries + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(self.config.timeout_seconds),
                    headers=self._headers(),
                    transport=self.transport,
                ) as client:
                    response = await client.post(
                        f"{self.config.base_url.rstrip('/')}/chat/completions", json=payload
                    )
                    response.raise_for_status()
                    content = response.json()["choices"][0]["message"]["content"]
                    return _parse_intent(content)
            except (httpx.TimeoutException, httpx.NetworkError) as exception:
                if attempt >= self.config.max_retries:
                    raise ProviderError("LLM_PROVIDER_TIMEOUT", retryable=True) from exception
                await asyncio.sleep(0.05 * (2**attempt))
            except (httpx.HTTPStatusError, ValueError, KeyError, json.JSONDecodeError) as exception:
                raise ProviderError("LLM_CLASSIFICATION_INVALID") from exception
        raise ProviderError("LLM_PROVIDER_UNAVAILABLE")

    async def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "temperature": 0,
        }
        if self.name != "lm-studio":
            payload["response_format"] = {"type": "json_object"}
        for attempt in range(self.config.max_retries + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(self.config.timeout_seconds),
                    headers=self._headers(),
                    transport=self.transport,
                ) as client:
                    response = await client.post(
                        f"{self.config.base_url.rstrip('/')}/chat/completions", json=payload
                    )
                    response.raise_for_status()
                    content = response.json()["choices"][0]["message"]["content"]
                    return _parse_json_object(content)
            except (httpx.TimeoutException, httpx.NetworkError) as exception:
                if attempt >= self.config.max_retries:
                    raise ProviderError("LLM_PROVIDER_TIMEOUT", retryable=True) from exception
                await asyncio.sleep(0.05 * (2**attempt))
            except (httpx.HTTPStatusError, ValueError, KeyError, json.JSONDecodeError) as exception:
                raise ProviderError("LLM_STRUCTURED_RESPONSE_INVALID") from exception
        raise ProviderError("LLM_PROVIDER_UNAVAILABLE")

    async def health(self) -> bool:
        try:
            await self.ensure_ready()
            return True
        except ProviderError:
            return False

    async def ensure_ready(self) -> None:
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(min(self.config.timeout_seconds, 5)),
                headers=self._headers(),
                transport=self.transport,
            ) as client:
                response = await client.get(f"{self.config.base_url.rstrip('/')}/models")
                response.raise_for_status()
                payload = response.json()
                model_ids = {
                    item.get("id")
                    for item in payload.get("data", [])
                    if isinstance(item, dict)
                }
        except (httpx.HTTPError, ValueError, AttributeError) as exception:
            raise ProviderError(
                "LLM_PROVIDER_UNAVAILABLE",
                retryable=True,
                message=(
                    f"Cannot reach the configured LLM provider at {self.config.base_url}. "
                    "For LM Studio, start its Local Server. Otherwise configure "
                    "LLM_PROVIDER=OPENAI_COMPATIBLE, LLM_BASE_URL, LLM_MODEL, and "
                    "export OPENAI_COMPATIBLE_API_KEY before start-all.sh."
                ),
            ) from exception
        if self.model not in model_ids:
            available = ", ".join(sorted(value for value in model_ids if value)) or "none"
            raise ProviderError(
                "LLM_MODEL_NOT_AVAILABLE",
                message=(
                    f"Configured model '{self.model}' is not available from "
                    f"{self.config.base_url}. Available models: {available}. "
                    "Load the model or update LLM_MODEL in the repository .env file."
                ),
            )


class LmStudioProvider(OpenAiCompatibleProvider):
    name = "lm-studio"


class DeterministicMockProvider:
    name = "deterministic-mock"
    model = "mock-v1"

    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        prompt = next(
            (message["content"] for message in reversed(messages) if message["role"] == "user"), ""
        )
        if "[fail]" in prompt:
            raise ProviderError("MOCK_PROVIDER_FAILURE")
        response = f"Mock response: {prompt}"
        for offset in range(0, len(response), 8):
            yield response[offset : offset + 8]

    async def classify(self, prompt: str) -> IntentType:
        lowered = prompt.rsplit("Current request:\n", maxsplit=1)[-1].lower()
        if any(word in lowered for word in (
            "predict", "forecast", "model", "classification", "tahmin", "sınıflandır",
        )):
            return IntentType.ML
        if any(word in lowered for word in (
            "report", "sum", "average", "group", "count", "rapor", "toplam", "ortalama",
        )):
            return IntentType.REPORT
        return IntentType.CONVERSATIONAL

    async def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        if "ENTITY_RESOLUTION_REQUEST=" in user_prompt:
            request = json.loads(user_prompt.split("ENTITY_RESOLUTION_REQUEST=", 1)[1])
            text = " ".join([
                request["currentRequest"],
                *[
                    item.get("content", "")
                    for item in request.get("conversation", [])
                    if item.get("role") == "user"
                ],
            ]).lower()
            scored = []
            for entity in request["authorizedEntities"]:
                terms = {
                    term
                    for value in [
                        entity.get("name", ""),
                        entity.get("description", ""),
                        *entity.get("columnNames", []),
                    ]
                    for term in re.findall(r"[a-zA-ZÀ-ž_]{3,}", value.lower())
                }
                scored.append((sum(term in text for term in terms), entity["entityId"]))
            scored.sort(reverse=True)
            if scored and scored[0][0] > 0 and (
                len(scored) == 1 or scored[0][0] > scored[1][0]
            ):
                return {"selectedEntityId": scored[0][1]}
            return {"selectedEntityId": None}
        if "APPROVED_ALGORITHM_REGISTRY=" in user_prompt:
            try:
                request = json.loads(user_prompt.split("AUTHORIZED_REQUEST=", 1)[1])
                schema = request["authorizedSchema"]
                numeric = {"INTEGER", "LONG", "DECIMAL"}
                features = [
                    item["columnName"] for item in schema["columns"]
                    if item["dataType"] in numeric
                ]
                target = next(
                    item["columnName"] for item in schema["columns"]
                    if item["dataType"] in numeric
                )
                features = [name for name in features if name != target]
                return {
                    "schemaVersion": "1.0",
                    "executionType": "ML",
                    "entityId": schema["entityId"],
                    "requestedLanguage": request["requestedLanguage"],
                    "requestSummary": "Deterministic mock ML execution",
                    "constraints": {"maxPreviewRows": 100, "timeoutSeconds": 300},
                    "payload": {
                        "problemType": "REGRESSION",
                        "algorithm": "LINEAR_REGRESSION",
                        "targetColumn": target,
                        "featureColumns": features,
                        "filters": [],
                        "split": {
                            "strategy": "RANDOM",
                            "trainingRatio": 0.8,
                            "seed": 42,
                        },
                        "parameters": {"maxIter": 30, "regParam": 0.0},
                        "candidateAlgorithms": [
                            {
                                "algorithm": "LINEAR_REGRESSION",
                                "parameterGrid": {
                                    "maxIter": [30, 60],
                                    "regParam": [0.0],
                                },
                            },
                            {
                                "algorithm": "RANDOM_FOREST_REGRESSOR",
                                "parameterGrid": {
                                    "numTrees": [20],
                                    "maxDepth": [5],
                                },
                            },
                        ],
                        "selection": {
                            "strategy": "TRAIN_VALIDATION_SPLIT",
                            "primaryMetric": "RMSE",
                            "maximumTrials": 3,
                            "trainingRatio": 0.7,
                            "validationRatio": 0.15,
                            "testRatio": 0.15,
                            "seed": 42,
                        },
                        "metrics": ["RMSE", "R2"],
                        "output": {
                            "includeFeatureImportance": True,
                            "includePredictionsPreview": True,
                        },
                    },
                }
            except (KeyError, StopIteration, IndexError, json.JSONDecodeError) as exception:
                raise ProviderError("MOCK_ML_ORDER_UNAVAILABLE") from exception
        marker = "AUTHORIZED_SCHEMA_JSON="
        try:
            metadata = json.loads(user_prompt.split(marker, 1)[1].split("\n", 1)[0])
            column = metadata["columns"][0]["columnName"]
            return {
                "schemaVersion": "1.0", "executionType": "REPORT",
                "entityId": metadata["entityId"],
                "requestedLanguage": metadata["requestedLanguage"],
                "requestSummary": "Deterministic mock report",
                "constraints": {"maxPreviewRows": 100, "timeoutSeconds": 300},
                "payload": {
                    "select": [{"column": column, "alias": column}], "filters": [],
                    "groupBy": [], "aggregations": [], "orderBy": [], "limit": 100,
                    "chartHints": [],
                },
            }
        except (KeyError, StopIteration, IndexError, json.JSONDecodeError) as exception:
            raise ProviderError("MOCK_REPORT_ORDER_UNAVAILABLE") from exception

    async def health(self) -> bool:
        return True


class ProviderRegistry:
    def resolve(self, config: EffectiveLlmConfiguration) -> ChatProvider:
        provider = config.provider.upper()
        if provider == "LM_STUDIO":
            return LmStudioProvider(config)
        if provider == "OPENAI_COMPATIBLE":
            api_key = os.environ.get("OPENAI_COMPATIBLE_API_KEY")
            if not api_key:
                raise ProviderError(
                    "LLM_API_KEY_MISSING",
                    message=(
                        "LLM_PROVIDER is OPENAI_COMPATIBLE but "
                        "the API key was not loaded from Vault. Export "
                        "OPENAI_COMPATIBLE_API_KEY before start-all.sh, or use "
                        "LM_STUDIO with a running Local Server."
                    ),
                )
            return OpenAiCompatibleProvider(
                config, api_key=api_key
            )
        raise ProviderError("LLM_PROVIDER_NOT_SUPPORTED")
