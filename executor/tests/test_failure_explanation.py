import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from kozmik_executor.chat.providers import ProviderError
from kozmik_executor.execution.failure_explanation import FailureExplainer
from kozmik_executor.execution.models import ExecutionCommand
from kozmik_executor.execution.worker import _spark_tuning_configuration_unsafe


class RecordingProvider:
    name = "recording"
    model = "recording"

    def __init__(self, fail: bool = False) -> None:
        self.messages = None
        self.fail = fail

    async def stream(self, messages):
        self.messages = messages
        if self.fail:
            raise ProviderError("LLM_PROVIDER_UNAVAILABLE")
        yield "The report mixed individual fields with an overall total. "
        yield "List records without aggregation or group the requested totals."


class Registry:
    def __init__(self, provider) -> None:
        self.provider = provider

    def resolve(self, config):
        return self.provider


def command(language: str = "en") -> ExecutionCommand:
    entity_id, actor_id = uuid4(), uuid4()
    return ExecutionCommand.model_validate({
        "schemaVersion": "1.0", "eventId": str(uuid4()),
        "correlationId": "failure-test", "executionId": str(uuid4()),
        "entityId": str(entity_id), "actorUserId": str(actor_id),
        "occurredAt": datetime.now(timezone.utc).isoformat(),
        "executionType": "REPORT",
        "authorization": {
            "actorUserId": str(actor_id),
            "roles": ["REPORTER"],
        },
        "configuration": {"llm": {
            "provider": "MOCK", "baseUrl": "http://unused", "model": "mock",
            "timeoutSeconds": 10, "maxRetries": 0, "maxContextMessages": 10,
            "maxContextCharacters": 1000,
        }},
        "order": {
            "schemaVersion": "1.0", "executionType": "REPORT",
            "entityId": str(entity_id),
            "requestedLanguage": language, "requestSummary": "Recent sales",
            "constraints": {"maxPreviewRows": 20, "timeoutSeconds": 30},
            "payload": {
                "select": [{"column": "sale_date"}, {"column": "region"}],
                "filters": [], "groupBy": [],
                "aggregations": [{
                    "function": "SUM", "column": "net_amount",
                    "alias": "net_amount_sum",
                }],
                "orderBy": [{"column": "sale_date", "direction": "DESC"}],
                "limit": 20, "chartHints": [],
            },
        },
    })


def test_failure_prompt_contains_only_sanitized_bounded_facts():
    provider = RecordingProvider()
    raw = RuntimeError(
        "SECRET_ROW customer=42 /private/bucket/path SELECT * password=hunter2")

    outcome = asyncio.run(FailureExplainer(Registry(provider)).explain(
        command(), raw, "SPARK_JOB_FAILED"))

    assert outcome.failure_code == "REPORT_ORDER_SHAPE_INVALID"
    assert outcome.explanation_status == "COMPLETED"
    prompt = provider.messages[1]["content"]
    assert "REPORT_ORDER_SHAPE_INVALID" in prompt
    assert "SECRET_ROW" not in prompt
    assert "/private/bucket/path" not in prompt
    assert "password" not in prompt
    assert "SELECT *" not in prompt


def test_temporal_group_output_is_not_misclassified_as_ungrouped_row_field():
    raw = command().model_dump(by_alias=True, mode="json")
    raw["order"]["payload"].update({
        "select": [{"column": "sale_date", "alias": "sale_month"}],
        "groupBy": [],
        "temporalGroupBy": [{
            "column": "sale_date", "alias": "sale_month", "granularity": "MONTH",
        }],
        "orderBy": [{"column": "sale_month", "direction": "ASC"}],
    })
    value = ExecutionCommand.model_validate(raw)

    code, _, _ = FailureExplainer().sanitize(
        value, RuntimeError("protected raw exception"), "SPARK_JOB_FAILED",
    )

    assert code == "SPARK_JOB_FAILED"


def test_provider_failure_returns_persistable_turkish_fallback():
    outcome = asyncio.run(FailureExplainer(Registry(
        RecordingProvider(fail=True))).explain(
            command("tr"), RuntimeError("raw stack"), "SPARK_JOB_FAILED"))

    assert outcome.explanation_status == "FAILED"
    assert outcome.language == "tr"
    assert "Rapor planı" in outcome.user_explanation
    assert "raw stack" not in outcome.user_explanation


def test_spark_serializer_stack_overflow_is_classified_as_unsafe_tuning():
    failure = RuntimeError(
        "Job aborted: Task serialization failed: java.lang.StackOverflowError")

    assert _spark_tuning_configuration_unsafe(failure)
