import httpx
import pytest

from kozmik_executor.control_plane import ControlPlaneClient


@pytest.mark.anyio
async def test_client_uses_credentials_loaded_after_module_initialization(monkeypatch) -> None:
    monkeypatch.delenv("INTERNAL_API_KEY", raising=False)
    monkeypatch.setenv("JAVA_BASE_URL", "http://backend.test")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "http://backend.test/internal/v1/configuration/effective"
        assert request.headers["X-Internal-API-Key"] == "vault-loaded-key"
        return httpx.Response(200, json={"status": "AVAILABLE"})

    client = ControlPlaneClient(transport=httpx.MockTransport(handler))

    # FastAPI loads Vault secrets during lifespan, after module-level clients
    # have already been constructed.
    monkeypatch.setenv("INTERNAL_API_KEY", "vault-loaded-key")

    response = await client.get("/internal/v1/configuration/effective")

    assert response.status_code == 200


@pytest.mark.anyio
async def test_client_uses_rotated_credentials_without_recreation(monkeypatch) -> None:
    observed_keys: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed_keys.append(request.headers["X-Internal-API-Key"])
        return httpx.Response(200)

    client = ControlPlaneClient(transport=httpx.MockTransport(handler))

    monkeypatch.setenv("INTERNAL_API_KEY", "first-key")
    await client.get("/internal/v1/health")
    monkeypatch.setenv("INTERNAL_API_KEY", "rotated-key")
    await client.get("/internal/v1/health")

    assert observed_keys == ["first-key", "rotated-key"]
