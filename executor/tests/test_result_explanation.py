import asyncio
import json
from datetime import datetime, timezone
from uuid import uuid4

from kozmik_executor.execution.explanation import ResultExplainer
from kozmik_executor.execution.models import ExecutionCommand


def command(language: str = "en") -> ExecutionCommand:
    entity_id = uuid4()
    return ExecutionCommand.model_validate({
        "schemaVersion": "1.0", "eventId": str(uuid4()),
        "correlationId": "summary-test", "executionId": str(uuid4()),
        "entityId": str(entity_id), "actorUserId": str(uuid4()),
        "occurredAt": datetime.now(timezone.utc).isoformat(),
        "executionType": "REPORT",
        "originalRequest": "Show the real user request with a monthly trend chart.",
        "dataSchema": {
            "entityId": str(entity_id),
            "columns": [{
                "columnName": "currency_code", "businessName": "Currency code",
                "dataType": "STRING", "categoricalValues": ["TRY"],
            }],
        },
        "authorization": {"roles": ["REPORTER"]},
        "configuration": {"llm": {
            "provider": "MOCK", "baseUrl": "http://unused", "model": "mock",
            "timeoutSeconds": 10, "maxRetries": 0, "maxContextMessages": 10,
            "maxContextCharacters": 1000,
        }},
        "order": {
            "schemaVersion": "1.0", "executionType": "REPORT",
            "entityId": str(entity_id), "requestedLanguage": language,
            "requestSummary": "Compare monthly call count and total charge.",
            "constraints": {"maxPreviewRows": 100, "timeoutSeconds": 300},
            "payload": {
                "select": [{"column": "month"}], "filters": [],
                "groupBy": ["month"], "aggregations": [{
                    "function": "COUNT", "column": None, "alias": "call_count",
                }], "orderBy": [], "limit": 100, "chartHints": [],
            },
        },
    })


class TextProvider:
    name = "recording"
    model = "recording"

    def __init__(self, response: str = "January had the highest call count.") -> None:
        self.response = response
        self.requests = []

    async def complete_text(self, system_prompt: str, user_prompt: str) -> str:
        self.requests.append((system_prompt, user_prompt))
        return self.response


class Registry:
    def __init__(self, provider: TextProvider) -> None:
        self.provider = provider

    def resolve(self, _configuration):
        return self.provider


def result(row_count: int) -> dict:
    rows = [
        {"month": datetime(2026, 1, 1, tzinfo=timezone.utc), "call_count": index}
        for index in range(min(row_count, 100))
    ]
    return {
        "rowCount": row_count,
        "preview": {
            "columns": [
                {"name": "month", "type": "TIMESTAMP"},
                {"name": "call_count", "type": "LONG"},
            ],
            "rows": rows,
        },
        "kpis": [{"code": "MAX_CALL_COUNT", "value": 157553}],
        "charts": [{"type": "LINE", "categories": [rows[0]["month"]]}] if rows else [],
        "warnings": [],
    }


def test_result_summary_sends_original_request_and_complete_small_result() -> None:
    provider = TextProvider()
    outcome = asyncio.run(ResultExplainer(Registry(provider)).explain(command(), result(100)))

    payload = json.loads(provider.requests[0][1])
    assert outcome.status == "COMPLETED"
    assert outcome.text == "January had the highest call count."
    assert payload["originalRequest"] == (
        "Show the real user request with a monthly trend chart."
    )
    assert payload["sourceSchema"]["columns"][0]["categoricalValues"] == ["TRY"]
    assert payload["approvedOrder"]["payload"]["groupBy"] == ["month"]
    assert payload["totalRowCount"] == 100
    assert len(payload["resultRows"]) == 100
    assert payload["resultRows"][0]["month"] == "2026-01-01T00:00:00Z"
    assert payload["resultInformation"]["kpis"][0]["value"] == 157553


def test_result_summary_omits_rows_only_when_complete_result_exceeds_100() -> None:
    provider = TextProvider()
    outcome = asyncio.run(ResultExplainer(Registry(provider)).explain(command(), result(101)))

    payload = json.loads(provider.requests[0][1])
    assert outcome.status == "COMPLETED"
    assert payload["totalRowCount"] == 101
    assert payload["resultRows"] is None
    assert payload["resultInformation"]["kpis"][0]["value"] == 157553


def test_result_summary_uses_requested_language_and_plain_text() -> None:
    provider = TextProvider("**Özet:** Ocak ayında çağrı sayısı en yüksek seviyedeydi.")
    outcome = asyncio.run(ResultExplainer(Registry(provider)).explain(
        command("tr"), result(1),
    ))

    assert outcome.text == "Ocak ayında çağrı sayısı en yüksek seviyedeydi."
    assert "in Turkish" in provider.requests[0][0]


def test_result_summary_failure_does_not_fail_the_analytical_result() -> None:
    class FailingProvider(TextProvider):
        async def complete_text(self, system_prompt: str, user_prompt: str) -> str:
            raise RuntimeError("provider unavailable")

    outcome = asyncio.run(ResultExplainer(Registry(FailingProvider())).explain(
        command(), result(1),
    ))

    assert outcome.status == "FAILED"
    assert outcome.text is None
    assert outcome.error_code == "RESULT_SUMMARY_INTERNAL_ERROR"
