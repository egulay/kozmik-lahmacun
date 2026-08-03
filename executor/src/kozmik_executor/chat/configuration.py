import httpx

from .models import EffectiveConfiguration
from .providers import ProviderError
from kozmik_executor.control_plane import ControlPlaneClient


class JavaConfigurationClient:
    def __init__(self) -> None:
        self.control_plane = ControlPlaneClient(timeout_seconds=5)

    async def load(self) -> EffectiveConfiguration:
        if not self.control_plane.api_key:
            raise ProviderError("EFFECTIVE_CONFIGURATION_UNAVAILABLE")
        try:
            response = await self.control_plane.get("/internal/v1/config/effective")
            response.raise_for_status()
            return EffectiveConfiguration.model_validate(response.json())
        except (httpx.HTTPError, ValueError) as exception:
            raise ProviderError("EFFECTIVE_CONFIGURATION_UNAVAILABLE", retryable=True) from exception
