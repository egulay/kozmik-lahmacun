import os

import httpx
import pytest

from kozmik_executor.secrets import VaultSecretError, load_runtime_secrets_from_vault


@pytest.mark.anyio
async def test_openai_secret_is_loaded_from_scoped_vault_path(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/secret/data/kozmik-executor"
        assert request.headers["X-Vault-Token"] == "executor-token"
        return httpx.Response(
            200,
            json={"data": {"data": {
                "INTERNAL_API_KEY": "internal-key",
                "KAFKA_MESSAGE_SIGNING_KEY": "s" * 64,
                "MINIO_ACCESS_KEY": "executor",
                "MINIO_SECRET_KEY": "minio-secret",
                "OPENAI_COMPATIBLE_API_KEY": "vault-key",
            }}},
        )

    class MockClient(httpx.AsyncClient):
        def __init__(self, **kwargs):
            super().__init__(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setenv("VAULT_ADDR", "http://vault.test")
    monkeypatch.setenv("VAULT_TOKEN", "executor-token")
    monkeypatch.delenv("OPENAI_COMPATIBLE_API_KEY", raising=False)
    monkeypatch.setattr(httpx, "AsyncClient", MockClient)

    await load_runtime_secrets_from_vault()

    assert os.environ["OPENAI_COMPATIBLE_API_KEY"] == "vault-key"
    assert os.environ["INTERNAL_API_KEY"] == "internal-key"


@pytest.mark.anyio
async def test_missing_vault_configuration_has_actionable_error(monkeypatch) -> None:
    monkeypatch.delenv("VAULT_ADDR", raising=False)
    monkeypatch.delenv("VAULT_TOKEN", raising=False)

    with pytest.raises(VaultSecretError, match="start-all.sh"):
        await load_runtime_secrets_from_vault()


@pytest.mark.anyio
async def test_missing_required_runtime_secret_is_rejected(monkeypatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"data": {}}})

    class MockClient(httpx.AsyncClient):
        def __init__(self, **kwargs):
            super().__init__(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setenv("VAULT_ADDR", "http://vault.test")
    monkeypatch.setenv("VAULT_TOKEN", "executor-token")
    monkeypatch.setattr(httpx, "AsyncClient", MockClient)

    with pytest.raises(VaultSecretError, match="INTERNAL_API_KEY"):
        await load_runtime_secrets_from_vault()
