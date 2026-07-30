import os
import sys
from unittest.mock import AsyncMock

import pytest

from kozmik_executor.chat import api
from kozmik_executor.chat.models import EffectiveConfiguration, EffectiveLlmConfiguration
from kozmik_executor.chat.providers import DeterministicMockProvider


# Ensure local Spark workers use the project interpreter with pandas/XGBoost installed.
os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def deterministic_effective_configuration(monkeypatch):
    monkeypatch.setenv("ALLOW_MOCK_LLM_PROVIDER", "true")
    effective = EffectiveConfiguration(
        schema_version="1.0",
        llm=EffectiveLlmConfiguration(
            provider="MOCK",
            base_url="http://unused.test/v1",
            model="mock-v1",
            timeout_seconds=2,
            max_retries=2,
            max_context_messages=20,
            max_context_characters=12_000,
        ),
    )
    monkeypatch.setattr(api.configuration_client, "load", AsyncMock(return_value=effective))
    monkeypatch.setattr(
        api.provider_registry,
        "resolve",
        lambda _config: DeterministicMockProvider(),
    )
    return effective
