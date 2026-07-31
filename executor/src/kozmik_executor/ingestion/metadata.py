import json
from pathlib import Path
from uuid import UUID

from pydantic import Field

from kozmik_executor.chat.api import configuration_client, provider_registry
from kozmik_executor.chat.models import ContractModel
from kozmik_executor.chat.providers import ProviderError

from .models import IngestionColumn, StreamEntityColumn, StreamEntityDescriptor

class MetadataColumnProposal(ContractModel):
    column_name: str
    business_name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=1000)
    business_name_tr: str = Field(min_length=1, max_length=200)
    description_tr: str = Field(min_length=1, max_length=1000)


class MetadataProposal(ContractModel):
    entity_name: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=2000)
    entity_name_tr: str = Field(min_length=1, max_length=160)
    description_tr: str = Field(min_length=1, max_length=2000)
    columns: list[MetadataColumnProposal]


class MetadataEnricher:
    async def enrich(
        self, entity_id: UUID, source_name: str, columns: list[IngestionColumn],
    ) -> StreamEntityDescriptor:
        effective = await configuration_client.load()
        provider = provider_registry.resolve(effective.llm)
        safe_structure = {
            "sourceName": Path(source_name).stem[:160],
            "columns": [
                {
                    "columnName": item.column_name,
                    "dataType": item.data_type,
                    "ordinalPosition": index + 1,
                }
                for index, item in enumerate(columns)
            ],
        }
        system = (
            "Generate governed business metadata from structural schema metadata only. "
            "Return one JSON INSTANCE matching the requested shape. Do not return or repeat "
            "the JSON Schema definition. Never request or infer raw row values. "
            "Never output SQL or code. Preserve every columnName exactly and in order. "
            "Describe the likely business meaning. Authorization and operation "
            "capabilities are owned by the Java control plane. Generate both English and "
            "natural Turkish display metadata; do not translate technical columnName values."
        )
        output_schema = MetadataProposal.model_json_schema(by_alias=True)
        prompt = (
            f"SAFE_SCHEMA_STRUCTURE={json.dumps(safe_structure, separators=(',', ':'))}\n"
            "Return an object with exactly these top-level fields: entityName, description, "
            "entityNameTr, descriptionTr, and columns. Each columns item must contain "
            "columnName, businessName, description, businessNameTr, and descriptionTr. "
            "The response must contain metadata values, not schema keywords.\n"
            f"REQUIRED_OUTPUT_SHAPE={json.dumps(output_schema, separators=(',', ':'))}"
        )
        try:
            response = await provider.complete_json(system, prompt)
            try:
                proposal = MetadataProposal.model_validate(response)
            except Exception:
                correction = (
                    f"SAFE_SCHEMA_STRUCTURE={json.dumps(safe_structure, separators=(',', ':'))}\n"
                    "The previous response was not a metadata instance. Return only a JSON "
                    "object containing populated English entityName and description, Turkish "
                    "entityNameTr and descriptionTr, plus one columns item per supplied column "
                    "with English and Turkish display metadata. Preserve each columnName exactly. "
                    "Do not include $defs, properties, required, title, type, or any other "
                    "JSON Schema keyword."
                )
                proposal = MetadataProposal.model_validate(
                    await provider.complete_json(system, correction))
        except Exception as exception:
            if isinstance(exception, ProviderError):
                raise
            raise ProviderError("METADATA_ENRICHMENT_INVALID", retryable=False) from exception
        if [item.column_name for item in proposal.columns] != [
            item.column_name for item in columns
        ]:
            raise ProviderError("METADATA_COLUMN_BINDING_MISMATCH", retryable=False)

        governed_columns: list[StreamEntityColumn] = []
        for index, (structural, suggested) in enumerate(
            zip(columns, proposal.columns, strict=True)
        ):
            governed_columns.append(StreamEntityColumn(
                columnName=structural.column_name,
                businessName=suggested.business_name,
                dataType=structural.data_type,
                description=suggested.description,
                ordinalPosition=index + 1,
                businessNameTr=suggested.business_name_tr,
                descriptionTr=suggested.description_tr,
                categoricalValues=structural.categorical_values,
            ))
        return StreamEntityDescriptor(
            id=entity_id,
            name=proposal.entity_name,
            description=proposal.description,
            columns=governed_columns,
            nameTr=proposal.entity_name_tr,
            descriptionTr=proposal.description_tr,
        )
