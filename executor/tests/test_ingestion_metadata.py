import asyncio
from uuid import uuid4

from kozmik_executor.chat.models import EffectiveConfiguration
from kozmik_executor.ingestion import metadata
from kozmik_executor.ingestion.metadata import MetadataEnricher
from kozmik_executor.ingestion.models import IngestionColumn


def test_llm_metadata_is_typed_and_identifier_policy_is_clamped(monkeypatch):
    class Configuration:
        async def load(self):
            return EffectiveConfiguration.model_validate({
                "schemaVersion": "1.0",
                "llm": {
                    "provider": "LM_STUDIO", "baseUrl": "http://localhost",
                    "model": "test", "timeoutSeconds": 30, "maxRetries": 0,
                    "maxContextMessages": 10, "maxContextCharacters": 10_000,
                },
            })

    class Provider:
        name = "test-provider"
        model = "test-model"

        async def complete_json(self, system_prompt, user_prompt):
            assert "raw row values" in system_prompt
            assert "records" not in user_prompt
            return {
                "entityName": "Customer Sales",
                "description": "Sales transactions by customer.",
                "entityNameTr": "Müşteri Satışları",
                "descriptionTr": "Müşterilere göre satış işlemleri.",
                "columns": [
                    {
                        "columnName": "customer_email",
                        "businessName": "Customer email",
                        "description": "Customer contact identifier",
                        "businessNameTr": "Müşteri e-postası",
                        "descriptionTr": "Müşteri iletişim tanımlayıcısı",
                    },
                    {
                        "columnName": "net_amount",
                        "businessName": "Net amount",
                        "description": "Net transaction amount",
                        "businessNameTr": "Net tutar",
                        "descriptionTr": "Net işlem tutarı",
                    },
                ],
            }

    class Registry:
        def resolve(self, _configuration):
            return Provider()

    monkeypatch.setattr(metadata, "configuration_client", Configuration())
    monkeypatch.setattr(metadata, "provider_registry", Registry())
    descriptor = asyncio.run(MetadataEnricher().enrich(
        uuid4(), "sales.csv", [
            IngestionColumn(columnName="customer_email", dataType="STRING"),
            IngestionColumn(columnName="net_amount", dataType="DECIMAL"),
        ],
    ))

    assert descriptor.columns[0].column_name == "customer_email"
    assert descriptor.columns[1].column_name == "net_amount"
    assert descriptor.description == "Sales transactions by customer."


def test_schema_echo_is_corrected_once(monkeypatch):
    class Configuration:
        async def load(self):
            return EffectiveConfiguration.model_validate({
                "schemaVersion": "1.0",
                "llm": {
                    "provider": "LM_STUDIO", "baseUrl": "http://localhost",
                    "model": "test", "timeoutSeconds": 30, "maxRetries": 0,
                    "maxContextMessages": 10, "maxContextCharacters": 10_000,
                },
            })

    class Provider:
        name = "test-provider"
        model = "test-model"

        def __init__(self):
            self.calls = 0

        async def complete_json(self, _system_prompt, user_prompt):
            self.calls += 1
            if self.calls == 1:
                return {"type": "object", "properties": {}}
            assert "Do not include $defs" in user_prompt
            return {
                "entityName": "Sales",
                "description": "Sales transactions.",
                "entityNameTr": "Satışlar",
                "descriptionTr": "Satış işlemleri.",
                "columns": [{
                    "columnName": "net_amount",
                    "businessName": "Net amount",
                    "description": "Net sales amount.",
                    "businessNameTr": "Net tutar",
                    "descriptionTr": "Net satış tutarı.",
                }],
            }

    provider = Provider()

    class Registry:
        def resolve(self, _configuration):
            return provider

    monkeypatch.setattr(metadata, "configuration_client", Configuration())
    monkeypatch.setattr(metadata, "provider_registry", Registry())

    descriptor = asyncio.run(MetadataEnricher().enrich(
        uuid4(), "sales.csv",
        [IngestionColumn(columnName="net_amount", dataType="DECIMAL")],
    ))

    assert provider.calls == 2
    assert descriptor.name == "Sales"
