from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from kozmik_executor.chat.models import ContractModel


class IngestionColumn(ContractModel):
    column_name: str
    data_type: Literal["STRING", "INTEGER", "LONG", "DECIMAL", "BOOLEAN", "DATE", "TIMESTAMP"]
    categorical_values: list[str] = Field(default_factory=list, max_length=32)


class IngestionSchema(ContractModel):
    schema_version: Literal["1.0"]
    entity_id: UUID
    columns: list[IngestionColumn]


class ImportStatusEvent(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    event_id: UUID
    correlation_id: str = Field(min_length=1, max_length=100)
    import_id: UUID
    source_event_id: UUID
    entity_id: UUID
    occurred_at: datetime
    source_type: Literal["MINIO_OBJECT_CREATED"] = "MINIO_OBJECT_CREATED"
    source_reference: str = Field(max_length=1200)
    stage: Literal["RECEIVED", "VALIDATING", "RUNNING", "WRITING_RESULTS", "COMPLETED", "FAILED"]
    status: Literal["RECEIVED", "VALIDATING", "RUNNING", "COMPLETED", "FAILED"]
    message_code: Literal[
        "IMPORT_RECEIVED", "IMPORT_VALIDATING", "IMPORT_SPARK_RUNNING",
        "IMPORT_WRITING_REFINED", "IMPORT_COMPLETED", "UNKNOWN_ENTITY",
        "INVALID_FILENAME", "SCHEMA_MISMATCH", "IMPORT_FAILED", "ARTIFACT_WRITE_FAILED",
    ]
    row_count: int | None = Field(default=None, ge=0)
    refined_bucket: str | None = None
    refined_object_key: str | None = None
    error_code: str | None = Field(default=None, max_length=120)
    error_message: str | None = Field(default=None, max_length=1000)


class StreamEntityColumn(ContractModel):
    column_name: str = Field(pattern=r"[A-Za-z_][A-Za-z0-9_]*", max_length=160)
    business_name: str = Field(min_length=1, max_length=200)
    data_type: Literal["STRING", "INTEGER", "LONG", "DECIMAL", "BOOLEAN", "DATE", "TIMESTAMP"]
    description: str | None = Field(default=None, max_length=4000)
    ordinal_position: int = Field(ge=1)
    business_name_tr: str | None = Field(default=None, max_length=200)
    description_tr: str | None = Field(default=None, max_length=4000)
    categorical_values: list[str] = Field(default_factory=list, max_length=32)


class StreamEntityDescriptor(ContractModel):
    id: UUID
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=4000)
    columns: list[StreamEntityColumn] = Field(min_length=1, max_length=500)
    name_tr: str | None = Field(default=None, max_length=160)
    description_tr: str | None = Field(default=None, max_length=4000)


class StreamIngestionChunk(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    chunk_id: UUID
    stream_id: UUID
    entity: StreamEntityDescriptor
    source_id: str = Field(min_length=1, max_length=120)
    produced_at: datetime
    sequence: int = Field(ge=0)
    records: list[dict[str, Any]] = Field(min_length=1, max_length=5000)


class StreamIngestionStatusEvent(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    event_id: UUID
    correlation_id: str = Field(min_length=1, max_length=100)
    stream_id: UUID
    chunk_id: UUID
    entity_id: UUID
    source_id: str = Field(min_length=1, max_length=120)
    topic: Literal["ingestion.records.v1"] = "ingestion.records.v1"
    sequence: int = Field(ge=0)
    kafka_partition: int = Field(ge=0)
    first_offset: int = Field(ge=0)
    last_offset: int = Field(ge=0)
    produced_at: datetime
    occurred_at: datetime
    stage: Literal["RECEIVED", "VALIDATING", "RUNNING", "WRITING_RESULTS", "COMPLETED", "FAILED"]
    message_code: Literal[
        "IMPORT_RECEIVED", "IMPORT_VALIDATING", "IMPORT_SPARK_RUNNING",
        "IMPORT_WRITING_REFINED", "IMPORT_COMPLETED", "UNKNOWN_ENTITY",
        "SCHEMA_MISMATCH", "IMPORT_FAILED", "ARTIFACT_WRITE_FAILED",
    ]
    batch_row_count: int | None = Field(default=None, ge=0)
    cumulative_row_count: int | None = Field(default=None, ge=0)
    refined_bucket: str | None = None
    refined_object_key: str | None = None
    error_code: str | None = Field(default=None, max_length=120)
