"""Single authenticated HTTP boundary from the executor to the Java control plane."""

import os
from typing import Any

import httpx


class ControlPlaneClient:
    def __init__(
        self,
        *,
        timeout_seconds: float = 10,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.timeout = httpx.Timeout(timeout_seconds)
        self.transport = transport

    @property
    def base_url(self) -> str:
        return os.getenv("JAVA_BASE_URL", "http://localhost:8080").rstrip("/")

    @property
    def api_key(self) -> str:
        # Vault secrets are loaded during FastAPI lifespan, after modules and
        # their client objects have been imported. Resolve credentials for each
        # request so startup and future secret rotation use the current value.
        return os.getenv("INTERNAL_API_KEY", "")

    async def get(self, path: str) -> httpx.Response:
        return await self._request("GET", path)

    async def post(self, path: str, document: Any) -> httpx.Response:
        return await self._request("POST", path, document)

    async def put(self, path: str, document: Any) -> httpx.Response:
        return await self._request("PUT", path, document)

    async def _request(
        self, method: str, path: str, document: Any | None = None,
    ) -> httpx.Response:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            transport=self.transport,
            headers={"X-Internal-API-Key": self.api_key},
        ) as client:
            return await client.request(method, path, json=document)
