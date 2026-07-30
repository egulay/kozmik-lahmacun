import asyncio
import logging
import os
import re
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from minio import Minio
from pydantic import BaseModel, ConfigDict, Field

from kozmik_executor.chat.api import _authenticate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/internal/v1/artifacts")
_BUCKET_PATTERN = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")


class ArtifactLocation(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    artifact_id: UUID = Field(alias="artifactId")
    bucket: str
    object_key: str = Field(alias="objectKey")


class ExecutionArtifactDeleteRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_version: str = Field(alias="schemaVersion", pattern=r"^1\.0$")
    execution_id: UUID = Field(alias="executionId")
    artifacts: list[ArtifactLocation] = Field(max_length=20)


def artifact_store() -> Minio:
    return Minio(
        os.getenv("MINIO_ENDPOINT", "localhost:9000"),
        access_key=os.getenv("MINIO_ACCESS_KEY", ""),
        secret_key=os.getenv("MINIO_SECRET_KEY", ""),
        secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
    )


@router.post("/delete")
async def delete_execution_artifacts(
    request: ExecutionArtifactDeleteRequest,
    store: Annotated[Minio, Depends(artifact_store)],
    x_internal_api_key: str | None = Header(default=None),
) -> dict[str, object]:
    _authenticate(x_internal_api_key)
    expected_prefix = f"executions/{request.execution_id}/"
    for artifact in request.artifacts:
        if (
            not _BUCKET_PATTERN.fullmatch(artifact.bucket)
            or not artifact.object_key.startswith(expected_prefix)
            or ".." in artifact.object_key.split("/")
        ):
            logger.warning(
                "artifact_delete_rejected executionId=%s artifactId=%s code=INVALID_LOCATION",
                request.execution_id, artifact.artifact_id,
            )
            raise HTTPException(status_code=422, detail="invalid execution artifact location")

    deleted: list[UUID] = []
    try:
        for artifact in request.artifacts:
            await asyncio.to_thread(
                store.remove_object, artifact.bucket, artifact.object_key)
            deleted.append(artifact.artifact_id)
    except Exception as exception:
        logger.exception(
            "artifact_delete_failed executionId=%s deletedCount=%s",
            request.execution_id, len(deleted),
        )
        raise HTTPException(
            status_code=502, detail="artifact storage deletion failed") from exception

    logger.info(
        "execution_artifacts_deleted executionId=%s artifactCount=%s",
        request.execution_id, len(deleted),
    )
    return {
        "schemaVersion": "1.0",
        "executionId": str(request.execution_id),
        "deletedArtifactIds": [str(item) for item in deleted],
    }
