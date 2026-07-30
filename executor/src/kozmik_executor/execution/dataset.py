import asyncio
import os
import re
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Literal
from uuid import UUID

import httpx
from minio import Minio
from pydantic import Field, ValidationError, model_validator

from kozmik_executor.chat.models import ContractModel
from kozmik_executor.execution.models import ExecutionCommand


class GovernedDataset(ContractModel):
    schema_version: Literal["1.0"]
    execution_id: UUID
    entity_id: UUID
    import_id: UUID | None = None
    stream_id: UUID | None = None
    through_sequence: int | None = Field(default=None, ge=0)
    format: Literal["PARQUET", "PARQUET_DATASET"]
    bucket: Literal["refined"]
    object_key: str = Field(min_length=1, max_length=1000)
    row_count: int = Field(ge=0)
    execution_type: Literal["REPORT", "ML"]
    actor_user_id: UUID
    execution_order: dict[str, Any]
    authorization_snapshot: dict[str, Any]
    configuration_snapshot: dict[str, Any]

    @model_validator(mode="after")
    def safe_object_key(self) -> "GovernedDataset":
        expected = (
            f"entities/{self.entity_id}/imports/{self.import_id}/"
            if self.format == "PARQUET"
            else f"entities/{self.entity_id}/streams/{self.stream_id}/"
        )
        safe_suffix = (
            self.format == "PARQUET" and self.object_key.endswith(".parquet")
        ) or (
            self.format == "PARQUET_DATASET" and self.object_key.endswith("/dataset")
        )
        if (
            (self.format == "PARQUET" and self.import_id is None)
            or (self.format == "PARQUET_DATASET"
                and (self.stream_id is None or self.through_sequence is None))
            or
            not self.object_key.startswith(expected)
            or not safe_suffix
            or re.fullmatch(r"[A-Za-z0-9._/-]+", self.object_key) is None
        ):
            raise ValueError("unsafe governed dataset object key")
        return self


class DatasetResolutionError(ValueError):
    pass


class GovernedDatasetResolver:
    def __init__(
        self,
        minio: Minio | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = os.getenv("JAVA_BASE_URL", "http://localhost:8080")
        self.api_key = os.getenv("INTERNAL_API_KEY", "")
        self.transport = transport
        self.minio = minio or Minio(
            os.getenv("MINIO_ENDPOINT", "localhost:9000"),
            access_key=os.getenv("MINIO_ACCESS_KEY", ""),
            secret_key=os.getenv("MINIO_SECRET_KEY", ""),
            secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
        )

    async def metadata(self, command: ExecutionCommand) -> GovernedDataset:
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(10), transport=self.transport,
            ) as client:
                response = await client.get(
                    f"{self.base_url.rstrip('/')}/internal/v1/executions/"
                    f"{command.execution_id}/dataset",
                    headers={"X-Internal-API-Key": self.api_key},
                )
            if response.status_code == 404:
                raise DatasetResolutionError("GOVERNED_DATASET_NOT_FOUND")
            response.raise_for_status()
            dataset = GovernedDataset.model_validate(response.json())
        except DatasetResolutionError:
            raise
        except ValidationError as exception:
            raise DatasetResolutionError(
                "GOVERNED_DATASET_BINDING_MISMATCH") from exception
        except (httpx.HTTPError, TypeError) as exception:
            raise DatasetResolutionError("GOVERNED_DATASET_NOT_FOUND") from exception
        if (
            dataset.execution_id != command.execution_id
            or dataset.entity_id != command.entity_id
            or dataset.execution_type != command.execution_type
            or dataset.actor_user_id != command.actor_user_id
            or dataset.execution_order
            != command.order.model_dump(by_alias=True, mode="json")
            or dataset.authorization_snapshot != command.authorization
            or dataset.configuration_snapshot != command.configuration
        ):
            raise DatasetResolutionError("GOVERNED_DATASET_BINDING_MISMATCH")
        return dataset

    @asynccontextmanager
    async def resolve(self, command: ExecutionCommand) -> AsyncIterator[dict[str, object]]:
        dataset = await self.metadata(command)
        with tempfile.TemporaryDirectory(prefix=f"kozmik-dataset-{command.execution_id}-") as path:
            local = Path(path) / (
                "dataset.parquet" if dataset.format == "PARQUET" else "dataset")
            try:
                if dataset.format == "PARQUET":
                    await asyncio.to_thread(
                        self.minio.fget_object, dataset.bucket,
                        dataset.object_key, str(local))
                else:
                    local.mkdir()
                    objects = await asyncio.to_thread(
                        lambda: list(self.minio.list_objects(
                            dataset.bucket, prefix=dataset.object_key + "/",
                            recursive=True)))
                    if not objects or any(
                        not item.object_name.endswith(".parquet") for item in objects
                    ):
                        raise DatasetResolutionError("GOVERNED_DATASET_NOT_FOUND")
                    selected = []
                    for item in objects:
                        match = re.search(r"/part-(\d{12})-[0-9a-fA-F-]{36}\.parquet$",
                                          item.object_name)
                        if match and int(match.group(1)) <= dataset.through_sequence:
                            selected.append(item)
                    if not selected:
                        raise DatasetResolutionError("GOVERNED_DATASET_NOT_FOUND")
                    for index, item in enumerate(selected):
                        await asyncio.to_thread(
                            self.minio.fget_object, dataset.bucket, item.object_name,
                            str(local / f"part-{index:012d}.parquet"))
            except Exception as exception:
                if isinstance(exception, DatasetResolutionError):
                    raise
                raise DatasetResolutionError("GOVERNED_DATASET_NOT_FOUND") from exception
            yield {
                "datasetUri": str(local),
                "datasetFormat": "parquet",
                "datasetImportId": (
                    str(dataset.import_id) if dataset.import_id else None),
                "datasetStreamId": (
                    str(dataset.stream_id) if dataset.stream_id else None),
                "datasetThroughSequence": dataset.through_sequence,
                "datasetRowCount": dataset.row_count,
            }
