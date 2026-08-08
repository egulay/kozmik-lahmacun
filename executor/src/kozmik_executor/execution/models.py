from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from kozmik_executor.chat.models import ContractModel
from kozmik_executor.planning.models import MlOrder, ReportOrder


class EventEnvelope(ContractModel):
    schema_version: Literal["1.0"]
    event_id: UUID
    correlation_id: str = Field(min_length=1, max_length=100)
    execution_id: UUID
    entity_id: UUID
    actor_user_id: UUID
    occurred_at: datetime


class ExecutionCommand(EventEnvelope):
    execution_type: Literal["REPORT", "ML"]
    original_request: str | None = Field(default=None, min_length=1, max_length=4_000)
    include_summary: bool = True
    data_schema: dict[str, Any] | None = None
    order: ReportOrder | MlOrder
    authorization: dict[str, Any]
    configuration: dict[str, Any]


class ExecutionControlCommand(EventEnvelope):
    operation: Literal["CANCEL"]

class ArtifactRetentionCommand(EventEnvelope):
    operation: Literal["DELETE_ARTIFACT"]
    artifact_id: UUID
    bucket: str = Field(min_length=1, max_length=100)
    object_key: str = Field(min_length=1, max_length=800)


class ArtifactRetentionEvent(ArtifactRetentionCommand):
    status: Literal["SUCCEEDED", "FAILED"]
    result_code: Literal["ARTIFACT_DELETED", "ARTIFACT_DELETE_FAILED"]


class ExecutionStatusEvent(EventEnvelope):
    stage: Literal[
        "QUEUED", "PREPARING", "VALIDATING", "RESOLVING_DATA", "TUNING",
        "RUNNING", "TRAINING",
        "WRITING_RESULTS", "SUMMARIZING", "COMPLETED", "FAILED",
        "CANCELLED", "TIMED_OUT",
    ]
    status: Literal["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED", "TIMED_OUT"]
    progress_percent: int = Field(ge=0, le=100)
    message_code: Literal[
        "EXECUTION_QUEUED", "EXECUTION_PREPARING", "EXECUTION_VALIDATING",
        "EXECUTION_ORDER_INVALID", "SCHEMA_VERSION_MISMATCH",
        "EXECUTION_TIMEOUT", "EXECUTION_CANCELLED", "EXECUTION_WORKER_FAILED",
        "EXECUTION_SPARK_RUNNING", "EXECUTION_WRITING_RESULTS",
        "EXECUTION_SPARK_PROGRESS",
        "EXECUTION_SUMMARIZING", "EXECUTION_REPORT_COMPLETED",
        "SPARK_JOB_FAILED", "SPARK_RUNTIME_UNAVAILABLE",
        "ML_TUNING_CONFIGURATION_UNSAFE", "ARTIFACT_WRITE_FAILED",
        "EXECUTION_ML_TRAINING",
        "EXECUTION_RESOLVING_DATA", "GOVERNED_DATASET_NOT_FOUND",
        "GOVERNED_DATASET_BINDING_MISMATCH",
        "EXECUTION_ML_TUNING",
    ]
    details: dict[str, Any] = Field(default_factory=dict)


class ExecutionResultNotification(EventEnvelope):
    status: Literal["SUCCEEDED"]
    result_code: Literal["EXECUTION_RESULT_READY"]
    row_count: int = Field(ge=0)
    preview: dict[str, Any]
    kpis: list[dict[str, Any]] = Field(max_length=20)
    charts: list[dict[str, Any]] = Field(max_length=5)
    warnings: list[dict[str, Any]] = Field(max_length=20)
    artifact: dict[str, Any]
    model_artifact: dict[str, Any] | None = None
    summary_status: Literal["COMPLETED", "FAILED", "SKIPPED"]
    result_summary: str | None = None
    summary_provider: str
    summary_provider_model: str
    summary_generated_at: datetime
    summary_error_code: str | None = None
