import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from kozmik_executor.execution.models import (
    ArtifactRetentionCommand,
    ExecutionCommand,
    ExecutionResultNotification,
)
from kozmik_executor.execution.worker import (
    EventLedger, KafkaExecutionWorker, TrustedReportWorker,
)


def command(configuration=None, include_summary=True) -> ExecutionCommand:
    entity_id = uuid4()
    actor_id = uuid4()
    return ExecutionCommand.model_validate({
        "schemaVersion": "1.0", "eventId": str(uuid4()), "correlationId": "worker-test",
        "executionId": str(uuid4()), "entityId": str(entity_id), "actorUserId": str(actor_id),
        "occurredAt": datetime.now(timezone.utc).isoformat(), "executionType": "REPORT",
        "includeSummary": include_summary,
        "authorization": {
            "actorUserId": str(actor_id),

            "roles": ["REPORTER"],
        },
        "configuration": configuration or {"timeoutSeconds": 300},
        "order": {
            "schemaVersion": "1.0", "executionType": "REPORT",
            "entityId": str(entity_id),
            "requestedLanguage": "en", "requestSummary": "Trusted report",
            "constraints": {"maxPreviewRows": 2, "timeoutSeconds": 300},
            "payload": {"select": [{"column": "amount"}], "filters": [], "groupBy": [],
                        "aggregations": [], "orderBy": [], "limit": 100, "chartHints": []},
        },
    })


class FakeExecutor:
    async def execute(self, execution_id, order, configuration, cancellation):
        return {
            "rowCount": 3,
            "preview": {"columns": [], "rows": [], "limit": 2, "truncated": True},
            "kpis": [], "charts": [],
            "warnings": [{"code": "RESULT_TRUNCATED",
                          "messageKey": "result.warning.truncated"}],
            "artifact": {"artifactId": str(uuid4()), "format": "PARQUET",
                         "bucket": "results",
                         "objectKey": f"executions/{execution_id}/result.parquet",
                         "sizeBytes": 42},
            "resultSummary": "Bounded deterministic summary",
        }


def test_worker_emits_deterministic_lifecycle_and_bounded_result():
    statuses = []
    results = []

    async def status(event):
        statuses.append(event)

    async def result(event):
        results.append(event)

    value = command()
    worker = TrustedReportWorker(status, result, FakeExecutor())
    asyncio.run(worker.execute(value))
    first_ids = [event.event_id for event in statuses] + [results[0].event_id]
    statuses.clear()
    results.clear()
    asyncio.run(worker.execute(value))
    assert first_ids == [event.event_id for event in statuses] + [results[0].event_id]
    assert statuses[-1].status == "SUCCEEDED"
    assert [item.stage for item in statuses] == [
        "QUEUED", "PREPARING", "VALIDATING", "RESOLVING_DATA", "RUNNING",
        "WRITING_RESULTS", "SUMMARIZING", "COMPLETED",
    ]
    assert results[0].preview["truncated"] is True
    assert results[0].artifact["format"] == "PARQUET"
    assert results[0].summary_status == "FAILED"
    assert results[0].summary_error_code == "RESULT_SUMMARY_INTERNAL_ERROR"
    assert results[0].summary_generated_at is not None

    unbounded = results[0].model_dump(by_alias=True, mode="json")
    unbounded["resultSummary"] = "Evidence-grounded explanation. " * 1000
    validated = ExecutionResultNotification.model_validate(unbounded)
    assert len(validated.result_summary) > 20_000



def test_event_ledger_suppresses_completed_duplicate(tmp_path):
    ledger = EventLedger(str(tmp_path / "events.sqlite3"))
    event_id = uuid4()
    assert ledger.completed(event_id) is False
    ledger.complete(event_id)
    ledger.complete(event_id)
    assert ledger.completed(event_id) is True


def test_worker_skips_summary_provider_when_summary_was_excluded():
    statuses = []
    results = []

    class ExplainerThatMustNotRun:
        async def explain(self, _command, _result):
            raise AssertionError("summary provider must not be called")

    async def status(event):
        statuses.append(event)

    async def result(event):
        results.append(event)

    worker = TrustedReportWorker(
        status, result, FakeExecutor(), explainer=ExplainerThatMustNotRun())
    asyncio.run(worker.execute(command(include_summary=False)))

    assert results[0].summary_status == "SKIPPED"
    assert results[0].result_summary is None
    assert results[0].summary_provider == "NOT_REQUESTED"
    assert "SUMMARIZING" not in [item.stage for item in statuses]


def test_artifact_retention_is_executed_by_python_and_reports_success(tmp_path):
    class FakeMinio:
        def __init__(self):
            self.removed = []

        def remove_object(self, bucket, object_key):
            self.removed.append((bucket, object_key))

    events = []

    async def send(topic, key, event):
        events.append((topic, key, event))

    worker = KafkaExecutionWorker.__new__(KafkaExecutionWorker)
    worker.minio = FakeMinio()
    worker.ledger = EventLedger(str(tmp_path / "retention-events.sqlite3"))
    worker.event_topic = "execution.events.v1"
    worker._send = send
    command_value = command()
    retention = ArtifactRetentionCommand(
        **command_value.model_dump(exclude={
            "execution_type", "original_request", "include_summary", "data_schema",
            "order", "authorization",
            "configuration",
        }),
        operation="DELETE_ARTIFACT", artifact_id=uuid4(), bucket="results",
        object_key=f"executions/{command_value.execution_id}/result.parquet",
    )

    assert asyncio.run(worker._delete_artifact(retention)) is True
    assert worker.minio.removed == [
        ("results", f"executions/{command_value.execution_id}/result.parquet")]
    assert events[0][2].status == "SUCCEEDED"
    assert events[0][2].result_code == "ARTIFACT_DELETED"
