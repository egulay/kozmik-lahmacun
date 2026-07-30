import os

import httpx

from .models import EffectiveConfiguration
from .providers import ProviderError


class JavaConfigurationClient:
    async def load(self) -> EffectiveConfiguration:
        base_url = os.environ.get("JAVA_BASE_URL", "http://localhost:8080")
        internal_key = os.environ.get("INTERNAL_API_KEY", "")
        if not internal_key:
            raise ProviderError("EFFECTIVE_CONFIGURATION_UNAVAILABLE")
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(5)) as client:
                response = await client.get(
                    f"{base_url.rstrip('/')}/internal/v1/config/effective",
                    headers={"X-Internal-API-Key": internal_key},
                )
                response.raise_for_status()
                return EffectiveConfiguration.model_validate(response.json())
        except (httpx.HTTPError, ValueError) as exception:
            raise ProviderError("EFFECTIVE_CONFIGURATION_UNAVAILABLE", retryable=True) from exception
