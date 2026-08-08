from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from kozmik_executor.artifacts import artifact_store, router


class RecordingStore:
    def __init__(self) -> None:
        self.deleted: list[tuple[str, str]] = []
        self.objects: dict[str, list[str]] = {}

    def remove_object(self, bucket: str, object_key: str) -> None:
        self.deleted.append((bucket, object_key))

    def list_objects(self, bucket: str, prefix: str = "", recursive: bool = False):
        del recursive
        return [type("StoredObject", (), {"object_name": name})()
                for name in self.objects.get(bucket, []) if name.startswith(prefix)]


def client(store: RecordingStore) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[artifact_store] = lambda: store
    return TestClient(app)


def test_deletes_only_execution_scoped_artifacts(monkeypatch) -> None:
    monkeypatch.setenv("INTERNAL_API_KEY", "internal-test-key")
    execution_id = uuid4()
    artifact_id = uuid4()
    store = RecordingStore()

    response = client(store).post(
        "/internal/v1/artifacts/delete",
        headers={"X-Internal-API-Key": "internal-test-key"},
        json={
            "schemaVersion": "1.0",
            "executionId": str(execution_id),
            "artifacts": [{
                "artifactId": str(artifact_id),
                "bucket": "results",
                "objectKey": f"executions/{execution_id}/{artifact_id}.parquet",
            }],
        },
    )

    assert response.status_code == 200
    assert store.deleted == [
        ("results", f"executions/{execution_id}/{artifact_id}.parquet")]


def test_rejects_an_artifact_outside_the_execution_prefix(monkeypatch) -> None:
    monkeypatch.setenv("INTERNAL_API_KEY", "internal-test-key")
    execution_id = uuid4()
    store = RecordingStore()

    response = client(store).post(
        "/internal/v1/artifacts/delete",
        headers={"X-Internal-API-Key": "internal-test-key"},
        json={
            "schemaVersion": "1.0",
            "executionId": str(execution_id),
            "artifacts": [{
                "artifactId": str(uuid4()),
                "bucket": "results",
                "objectKey": "governed/another-entity/data.parquet",
            }],
        },
    )

    assert response.status_code == 422
    assert store.deleted == []


def test_requires_internal_authentication(monkeypatch) -> None:
    monkeypatch.setenv("INTERNAL_API_KEY", "internal-test-key")
    response = client(RecordingStore()).post(
        "/internal/v1/artifacts/delete",
        json={
            "schemaVersion": "1.0",
            "executionId": str(uuid4()),
            "artifacts": [],
        },
    )
    assert response.status_code == 401


def test_deletes_all_objects_bound_to_a_retired_entity(monkeypatch) -> None:
    monkeypatch.setenv("INTERNAL_API_KEY", "internal-test-key")
    entity_id = uuid4()
    store = RecordingStore()
    store.objects = {
        "refined": [
            f"entities/{entity_id}/imports/one.parquet",
            f"entities/{entity_id}/streams/two.parquet",
            f"entities/{uuid4()}/imports/keep.parquet",
        ],
        "raw": [
            f"incoming/sales_{entity_id}_20260808.csv",
            "incoming/keep.csv",
        ],
    }

    response = client(store).post(
        "/internal/v1/artifacts/entities/delete",
        headers={"X-Internal-API-Key": "internal-test-key"},
        json={"schemaVersion": "1.0", "entityId": str(entity_id)},
    )

    assert response.status_code == 200
    assert set(store.deleted) == {
        ("refined", f"entities/{entity_id}/imports/one.parquet"),
        ("refined", f"entities/{entity_id}/streams/two.parquet"),
        ("raw", f"incoming/sales_{entity_id}_20260808.csv"),
    }
