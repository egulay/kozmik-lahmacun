import asyncio
from decimal import Decimal
from datetime import datetime, timezone
from uuid import uuid4

from kozmik_executor.execution.explanation import ResultExplainer, SummaryFacts
from kozmik_executor.execution.models import ExecutionCommand
from kozmik_executor.chat.providers import ProviderError


def command(language="en"):
    entity_id = uuid4()
    return ExecutionCommand.model_validate({
        "schemaVersion": "1.0", "eventId": str(uuid4()), "correlationId": "summary-test",
        "executionId": str(uuid4()), "entityId": str(entity_id), "actorUserId": str(uuid4()),
        "occurredAt": datetime.now(timezone.utc).isoformat(), "executionType": "REPORT",
        "authorization": {"roles": ["REPORTER"]},
        "configuration": {"llm": {
            "provider": "MOCK", "baseUrl": "http://unused", "model": "mock",
            "timeoutSeconds": 10, "maxRetries": 0, "maxContextMessages": 10,
            "maxContextCharacters": 1000,
        }},
        "order": {
            "schemaVersion": "1.0", "executionType": "REPORT",
            "entityId": str(entity_id),
            "requestedLanguage": language, "requestSummary": "Sales",
            "constraints": {"maxPreviewRows": 10, "timeoutSeconds": 30},
            "payload": {"select": [{"column": "amount"}], "filters": [], "groupBy": [],
                        "aggregations": [], "orderBy": [], "limit": 10, "chartHints": []},
        },
    })


def grouped_report_command(language="en"):
    raw = command(language).model_dump(by_alias=True, mode="json")
    raw["order"]["payload"] = {
        "select": [{"column": "region"}],
        "filters": [],
        "groupBy": ["region"],
        "aggregations": [{
            "function": "SUM", "column": "amount", "alias": "total_sales",
        }, {
            "function": "AVG", "column": "discount", "alias": "avg_discount",
        }],
        "orderBy": [{"column": "total_sales", "direction": "DESC"}],
        "limit": 10,
        "chartHints": [],
    }
    return ExecutionCommand.model_validate(raw)


class RecordingProvider:
    name = "recording"
    model = "recording"

    def __init__(self, fail=False):
        self.messages = None
        self.fail = fail

    async def stream(self, messages):
        self.messages = messages
        if self.fail:
            raise ProviderError("LLM_PROVIDER_UNAVAILABLE")
        yield "The leading region has the strongest revenue result in the supplied comparison."


class StubbornTechnicalProvider(RecordingProvider):
    def __init__(self):
        super().__init__()
        self.calls = 0

    async def stream(self, messages):
        self.calls += 1
        yield "The model used GBT with R2 and 20 trials for forecasting."


class EmptyFactsProvider(RecordingProvider):
    def __init__(self):
        super().__init__()
        self.calls = 0

    async def stream(self, messages):
        self.calls += 1
        self.messages = messages
        if self.calls == 1:
            yield "This decision summary does not contain any governed facts to analyze."
        else:
            yield "Marmara leads the regional comparison. The result covers only the selected scope."


class TurkishEmptyFactsProvider(RecordingProvider):
    def __init__(self):
        super().__init__()
        self.calls = 0

    async def stream(self, messages):
        self.calls += 1
        self.messages = messages
        if self.calls == 1:
            yield "Bu rapor somut veri sonuçlarını içermez ve veri seti boştur."
        else:
            yield "Bölgesel karşılaştırmada Marmara öndedir. Sonuç yalnızca seçilen kapsamı yansıtır."


class MissingMeasuresProvider(RecordingProvider):
    def __init__(self):
        super().__init__()
        self.calls = 0

    async def stream(self, messages):
        self.calls += 1
        self.messages = messages
        if self.calls < 3:
            yield (
                "The report shows five regional breakdowns without specific quantitative "
                "measures. No approved drivers or quantitative facts are provided. The "
                "analysis lacks concrete performance metrics."
            )
        else:
            yield (
                "Marmara leads with total sales of 6,525,519.3 and an average discount of "
                "zero. The comparison covers only the selected sales scope."
            )


class Registry:
    def __init__(self, provider):
        self.provider = provider

    def resolve(self, config):
        return self.provider


def result():
    return {
        "rowCount": 500,
        "preview": {
            "columns": [{"name": "customer_id", "type": "STRING"}],
            "rows": [{"customer_id": "SECRET-CUSTOMER-42", "amount": 999}],
            "limit": 1, "truncated": True,
        },
        "kpis": [{"code": "TOTAL_REVENUE", "labelKey": "result.kpi.revenue",
                  "value": 12345.0, "unit": "TRY", "customerId": "SECRET-CUSTOMER-42"}],
        "charts": [{
            "chartId": "feature-importance",
            "categories": ["unit_price", "quantity"],
            "series": [{"name": "importance", "data": [0.6, 0.4]}],
        }],
        "warnings": [{"code": "RESULT_TRUNCATED",
                      "messageKey": "result.warning.truncated", "raw": "SECRET-ROW"}],
    }


def test_summary_prompt_excludes_raw_preview_rows_and_unapproved_fields():
    provider = RecordingProvider()
    outcome = asyncio.run(ResultExplainer(Registry(provider)).explain(command(), result()))
    assert outcome.status == "COMPLETED"
    prompt = provider.messages[1]["content"]
    assert "TOTAL_REVENUE" in prompt
    assert "RESULT_TRUNCATED" in prompt
    assert "SECRET-CUSTOMER-42" not in prompt
    assert "SECRET-ROW" not in prompt
    assert '"preview"' not in prompt
    assert '"rows"' not in prompt
    assert '"drivers":[{"feature":"unit_price","importance":0.6}' in prompt
    system_prompt = provider.messages[0]["content"]
    assert "You may state these approved aggregate values" in system_prompt
    assert "bounded grouped aggregates, not raw source rows" in system_prompt
    assert "Never convert R2" in system_prompt
    assert "without adding a directional recommendation" in system_prompt


def test_turkish_instruction_and_provider_failure_are_nonfatal():
    provider = RecordingProvider(fail=True)
    outcome = asyncio.run(ResultExplainer(Registry(provider)).explain(command("tr"), result()))
    assert outcome.status == "FAILED"
    assert outcome.text is None
    assert "Turkish" in provider.messages[0]["content"]


def test_repeated_technical_summary_is_rejected_instead_of_presenting_a_fallback_as_llm_text():
    provider = StubbornTechnicalProvider()

    outcome = asyncio.run(ResultExplainer(Registry(provider)).explain(command(), result()))

    assert provider.calls == 3
    assert outcome.status == "FAILED"
    assert outcome.text is None


def test_plain_language_ml_prediction_wording_is_not_rejected_as_technical():
    summary = (
        "The predictive model estimates expected sales consistently from the available order "
        "information. Price and quantity have the strongest influence, while discount has a "
        "smaller effect. Management can use the forecast to compare planned orders, but it "
        "does not guarantee future demand or profit."
    )

    assert ResultExplainer._management_violations(summary) == []


def test_what_if_warning_is_not_repeated_in_management_summary():
    facts = SummaryFacts.model_validate({
        "executionType": "ML", "language": "en", "rowCount": 100,
        "algorithm": "GBT_REGRESSOR", "target": "net_amount",
        "features": ["quantity"], "drivers": [], "facts": [],
        "warnings": [{"code": "WHAT_IF_NOT_CAUSAL",
                      "messageKey": "result.warning.whatIfNotCausal"}],
    })
    duplicated = (
        "This analysis does not prove causation. A controlled experiment is needed because "
        "competitors or market conditions could change."
    )
    decision_focused = (
        "Among the tested comparisons, the quantity increase produced the strongest predicted "
        "net-sales result and is the clearest option for a limited pilot."
    )

    assert ResultExplainer._warning_duplication_violations(duplicated, facts)
    assert ResultExplainer._warning_duplication_violations(decision_focused, facts) == []


def test_grouped_report_passes_only_bounded_aggregate_breakdown_and_repairs_empty_claim():
    provider = EmptyFactsProvider()
    grouped_result = result()
    grouped_result["preview"] = {
        "columns": [],
        "rows": [
            {"region": "Marmara", "total_sales": 1200, "customer_id": "SECRET-1"},
            {"region": "Ege", "total_sales": 900, "customer_id": "SECRET-2"},
        ],
        "limit": 10,
        "truncated": False,
    }
    outcome = asyncio.run(ResultExplainer(Registry(provider)).explain(
        grouped_report_command(), grouped_result))

    prompt = provider.messages[1]["content"]
    assert '"reportBreakdown":[{"dimensions":{"region":"Marmara"}' in prompt
    assert '"measures":{"total_sales":1200}' in prompt
    assert "SECRET-1" not in prompt
    assert "SECRET-2" not in prompt
    assert outcome.status == "COMPLETED"
    assert outcome.text is not None
    assert "does not contain any governed facts" not in outcome.text
    assert "Marmara" in outcome.text
    assert provider.calls == 2


def test_turkish_empty_facts_claim_is_replaced_with_grounded_breakdown():
    provider = TurkishEmptyFactsProvider()
    grouped_result = result()
    grouped_result["preview"] = {
        "columns": [],
        "rows": [{"region": "Marmara", "total_sales": 1200}],
        "limit": 10,
        "truncated": False,
    }

    outcome = asyncio.run(ResultExplainer(Registry(provider)).explain(
        grouped_report_command("tr"), grouped_result))

    assert outcome.status == "COMPLETED"
    assert "somut veri sonuçlarını içermez" not in outcome.text
    assert "Marmara" in outcome.text
    assert provider.calls == 2


def test_decimal_string_aggregates_cannot_be_described_as_missing():
    provider = MissingMeasuresProvider()
    grouped_result = result()
    grouped_result["preview"] = {
        "columns": [],
        "rows": [
            {"region": "Marmara", "total_sales": Decimal("6525519.300000"),
             "avg_discount": Decimal("0E-10")},
            {"region": "Ege", "total_sales": Decimal("6403745.740000"),
             "avg_discount": Decimal("0.025")},
        ],
        "limit": 10,
        "truncated": False,
    }

    outcome = asyncio.run(ResultExplainer(Registry(provider)).explain(
        grouped_report_command(), grouped_result))

    assert outcome.status == "COMPLETED"
    assert outcome.text is not None
    assert "without specific quantitative measures" not in outcome.text
    assert "lacks concrete performance metrics" not in outcome.text
    assert "Marmara" in outcome.text
    assert "6,525,519.3" in outcome.text
    assert "average discount of zero" in outcome.text
    assert provider.calls == 3


def test_grounded_summary_recommends_only_calculated_best_scenario():
    facts = SummaryFacts.model_validate({
        "executionType": "ML", "language": "en", "rowCount": 100,
        "algorithm": "GBT_REGRESSOR", "target": "net_amount",
        "features": ["unit_price"], "drivers": [], "facts": [], "warnings": [],
        "scenarioObjective": "MAXIMIZE_TARGET",
        "scenarios": [
            {"code": "PRICE_UP", "changes": [
                {"column": "unit_price", "percentChange": 5},
            ], "deltaPercent": 4.2},
            {"code": "PRICE_DOWN", "changes": [
                {"column": "unit_price", "percentChange": -5},
            ], "deltaPercent": -4.1},
        ],
    })

    summary = ResultExplainer._grounded_management_fallback(facts)

    assert "Under the tested assumptions" in summary
    assert "unit price was relatively increased by 5%" in summary
    assert "+4.20%" in summary
    assert "limited, controlled business test" in summary
    assert "demand, cost, profit" not in summary
    assert "competitor reactions" not in summary
