import asyncio
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from kozmik_executor.execution.dataset import (
    DatasetResolutionError,
    GovernedDatasetResolver,
)
from kozmik_executor.execution.models import ExecutionCommand


def command() -> ExecutionCommand:
    entity_id, actor_id = uuid4(), uuid4()
    return ExecutionCommand.model_validate({
        "schemaVersion": "1.0",
        "eventId": str(uuid4()),
        "correlationId": "dataset-test",
        "executionId": str(uuid4()),
        "entityId": str(entity_id),
        "actorUserId": str(actor_id),
        "occurredAt": datetime.now(timezone.utc).isoformat(),
        "executionType": "REPORT",
        "authorization": {
            "actorUserId": str(actor_id),

            "roles": ["REPORTER"],
        },
        "configuration": {"execution": {"timeoutSeconds": 60}},
        "order": {
            "schemaVersion": "1.0",
            "executionType": "REPORT",
            "entityId": str(entity_id),

            "requestedLanguage": "en",
            "requestSummary": "Governed report",
            "constraints": {"maxPreviewRows": 10, "timeoutSeconds": 60},
            "payload": {
                "select": [{"column": "amount"}],
                "filters": [],
                "groupBy": [],
                "aggregations": [],
                "orderBy": [],
                "limit": 10,
                "chartHints": [],
            },
        },
    })


class RecordingMinio:
    def __init__(self) -> None:
        self.download = None

    def fget_object(self, bucket, object_key, path):
        self.download = (bucket, object_key)
        Path(path).write_bytes(b"PAR1-governed-test")


class DatasetObject:
    def __init__(self, object_name):
        self.object_name = object_name


class RecordingDatasetMinio(RecordingMinio):
    def list_objects(self, bucket, prefix, recursive):
        return [
            DatasetObject(prefix + "part-file-"
                          "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1.parquet"),
            DatasetObject(prefix + "part-stream-bbbbbbbb-bbbb-4bbb-8bbb-"
                          "bbbbbbbbbbb1-000000000001-"
                          "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2.parquet"),
            DatasetObject(prefix + "part-file-"
                          "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa3.parquet"),
        ]

    def fget_object(self, bucket, object_key, path):
        self.download = (bucket, object_key)
        Path(path).write_bytes(b"PAR1-governed-part")


def response(value: ExecutionCommand, *, entity_id=None):
    import_id = uuid4()
    return {
        "schemaVersion": "1.0",
        "executionId": str(value.execution_id),
        "entityId": str(entity_id or value.entity_id),

        "importId": str(import_id),
        "format": "PARQUET_DATASET",
        "bucket": "refined",
        "objectKey": f"entities/{entity_id or value.entity_id}/dataset",
        "rowCount": 42,
        "executionType": value.execution_type,
        "actorUserId": str(value.actor_user_id),
        "executionOrder": value.order.model_dump(by_alias=True, mode="json"),
        "authorizationSnapshot": value.authorization,
        "configurationSnapshot": value.configuration,
    }


def dataset_response(value: ExecutionCommand):
    result = response(value)
    stream_id = uuid4()
    result["format"] = "PARQUET_DATASET"
    result["importId"] = None
    result["streamId"] = str(stream_id)
    result["throughSequence"] = 1
    result["objectKey"] = f"entities/{value.entity_id}/dataset"
    return result


def test_exact_execution_entity_and_schema_resolve_to_local_governed_parquet(monkeypatch):
    value = command()
    requested = []

    def handler(request):
        requested.append(request)
        return httpx.Response(200, json=response(value))

    monkeypatch.setenv("INTERNAL_API_KEY", "internal-test-key")
    store = RecordingDatasetMinio()
    resolver = GovernedDatasetResolver(
        minio=store, transport=httpx.MockTransport(handler))

    async def resolve():
        async with resolver.resolve(value) as configuration:
            parts = sorted(Path(configuration["datasetUri"]).glob("*.parquet"))
            assert len(parts) == 3
            assert all(part.read_bytes().startswith(b"PAR1") for part in parts)
            assert configuration["datasetFormat"] == "parquet"
            assert configuration["datasetRowCount"] == 42
            return configuration["datasetUri"]

    temporary_path = asyncio.run(resolve())
    assert not Path(temporary_path).exists()
    assert requested[0].url.path == (
        f"/internal/v1/executions/{value.execution_id}/dataset")
    assert requested[0].headers["X-Internal-API-Key"] == "internal-test-key"
    assert store.download[0] == "refined"


def test_mismatched_entity_metadata_is_rejected_before_minio_access(monkeypatch):
    value = command()
    wrong_entity = uuid4()
    monkeypatch.setenv("INTERNAL_API_KEY", "internal-test-key")
    store = RecordingMinio()
    resolver = GovernedDatasetResolver(
        minio=store,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json=response(value, entity_id=wrong_entity))),
    )
    with pytest.raises(DatasetResolutionError) as error:
        asyncio.run(resolver.metadata(value))
    assert str(error.value) == "GOVERNED_DATASET_BINDING_MISMATCH"
    assert store.download is None


def test_parquet_dataset_prefix_downloads_all_governed_parts(monkeypatch):
    value = command()
    monkeypatch.setenv("INTERNAL_API_KEY", "internal-test-key")
    store = RecordingDatasetMinio()
    resolver = GovernedDatasetResolver(
        minio=store,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=dataset_response(value))),
    )

    async def resolve():
        async with resolver.resolve(value) as configuration:
            parts = sorted(Path(configuration["datasetUri"]).glob("*.parquet"))
            assert len(parts) == 3
            assert all(part.read_bytes().startswith(b"PAR1") for part in parts)

    asyncio.run(resolve())


def test_missing_governed_dataset_has_stable_failure_code(monkeypatch):
    value = command()
    monkeypatch.setenv("INTERNAL_API_KEY", "internal-test-key")
    resolver = GovernedDatasetResolver(
        minio=RecordingMinio(),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(404, json={"code": "NOT_FOUND"})),
    )
    with pytest.raises(DatasetResolutionError) as error:
        asyncio.run(resolver.metadata(value))
    assert str(error.value) == "GOVERNED_DATASET_NOT_FOUND"


def test_tampered_execution_order_is_rejected_against_java_snapshot(monkeypatch):
    value = command()
    authoritative = response(value)
    value.order.payload.select[0].column = "secret_column"
    monkeypatch.setenv("INTERNAL_API_KEY", "internal-test-key")
    resolver = GovernedDatasetResolver(
        minio=RecordingMinio(),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=authoritative)
        ),
    )

    with pytest.raises(DatasetResolutionError) as error:
        asyncio.run(resolver.metadata(value))

    assert str(error.value) == "GOVERNED_DATASET_BINDING_MISMATCH"
