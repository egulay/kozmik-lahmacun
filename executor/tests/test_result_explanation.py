import asyncio
from decimal import Decimal
from datetime import datetime, timezone
from uuid import uuid4

import pytest

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
            yield (
                "Marmara leads the regional comparison, while Ege has the lowest result. "
                "The result covers only the selected scope."
            )


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
                "zero, while Ege has the lowest total sales. The comparison covers only the "
                "selected sales scope."
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
    assert "RESULT_TRUNCATED" not in prompt
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


def test_long_execution_objective_is_bounded_before_summary_validation():
    execution = command().model_copy(deep=True)
    execution.order.request_summary = "Compare sales performance. " * 40

    facts = ResultExplainer().build_facts(execution, result())

    assert facts.objective is not None
    assert len(facts.objective) == 500


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


def test_management_summary_removes_provider_template_labels_and_markdown():
    summary = (
        "**Decision Summary** Web generated the highest net sales. "
        "**Approved Warnings** None"
    )

    assert ResultExplainer._clean_management_summary(summary) == (
        "Web generated the highest net sales."
    )


def test_report_summary_rejects_invented_euro_currency() -> None:
    facts = SummaryFacts.model_validate({
        "executionType": "REPORT",
        "language": "tr",
        "rowCount": 12,
        "objective": "Aylık toplam net satışları göster",
        "features": [],
        "drivers": [],
        "scenarios": [],
        "reportBreakdown": [
            {"dimensions": {"month": "2026-08"},
             "measures": {"total_net_sales": 2663788.27}},
        ],
        "reportHighlights": [],
        "facts": [],
        "warnings": [],
    })
    summary = (
        "Ağustos ayında toplam net satış 2,66 milyon euro ile en yüksek seviyeye ulaştı."
    )

    assert ResultExplainer._unit_grounding_violations(summary, facts) == [
        "do not invent a currency or unit absent from approved fact units"
    ]


def test_report_summary_accepts_explicitly_approved_currency_unit() -> None:
    facts = SummaryFacts.model_validate({
        "executionType": "REPORT",
        "language": "tr",
        "rowCount": 1,
        "objective": "Toplam satış",
        "features": [],
        "drivers": [],
        "scenarios": [],
        "reportBreakdown": [],
        "reportHighlights": [],
        "facts": [{"code": "TOTAL", "value": 100, "unit": "TRY"}],
        "warnings": [],
    })

    assert ResultExplainer._unit_grounding_violations(
        "Toplam satış 100 Türk lirasıdır.", facts
    ) == []


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


def test_report_comparison_contains_complete_business_range() -> None:
    grouped_result = result()
    grouped_result["preview"] = {
        "columns": [],
        "rows": [
            {"region": "Marmara", "total_sales": 1200, "avg_discount": 0.02},
            {"region": "Ege", "total_sales": 900, "avg_discount": 0.03},
            {"region": "Karadeniz", "total_sales": 600, "avg_discount": 0.04},
        ],
        "limit": 10,
        "truncated": False,
    }

    facts = ResultExplainer().build_facts(grouped_report_command(), grouped_result)
    comparison = next(
        item for item in facts.report_comparisons if item.measure == "total_sales"
    )

    assert comparison.highest_dimensions == {"region": "Marmara"}
    assert comparison.lowest_dimensions == {"region": "Karadeniz"}
    assert comparison.highest_value == 1200
    assert comparison.lowest_value == 600
    assert comparison.absolute_difference == 600
    assert comparison.percentage_difference == 100
    assert comparison.highest_share_percent == pytest.approx(44.4444, rel=1e-4)
    grounded = ResultExplainer._grounded_management_fallback(facts)
    assert "Marmara" in grounded
    assert "Karadeniz" in grounded
    assert "highest at 1,200" in grounded
    assert "lowest at 600" in grounded


def test_report_comparison_requires_both_strongest_and_weakest_group() -> None:
    facts = SummaryFacts.model_validate({
        "executionType": "REPORT", "language": "en", "rowCount": 3,
        "facts": [], "warnings": [],
        "reportComparisons": [{
            "measure": "total_sales",
            "highestDimensions": {"region": "Marmara"}, "highestValue": 1200,
            "lowestDimensions": {"region": "Karadeniz"}, "lowestValue": 600,
            "absoluteDifference": 600, "percentageDifference": 100,
            "highestSharePercent": 44.44, "groupCount": 3,
        }],
    })

    assert ResultExplainer._report_comparison_violations(
        "Marmara generated the highest result.", facts
    ) == ["identify the lowest group from reportComparisons"]
    assert ResultExplainer._report_comparison_violations(
        "Marmara was highest and Karadeniz was lowest.", facts
    ) == []


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


def test_report_highlights_are_bounded_aggregates_and_allow_absence_of_anomaly_wording():
    result_document = result()
    result_document["charts"] = [{
        "chartId": "chart-1", "type": "LINE", "categoryField": "call_month",
        "categories": ["2026-01", "2026-02"],
        "series": [
            {"name": "VOICE", "data": [30, 40]},
            {"name": "SMS", "data": [10, 5]},
        ],
    }]

    facts = ResultExplainer().build_facts(grouped_report_command(), result_document)

    assert facts.report_highlights[0].leading_category == "2026-02"
    assert facts.report_highlights[0].value == 45
    assert ResultExplainer._grounding_violations(
        "February was busiest, and no unusual duration pattern was identified.", facts,
    ) == []


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
    assert "-4.10%" in summary
    assert "limited, controlled business test" in summary
    assert "demand, cost, profit" not in summary
    assert "competitor reactions" not in summary


def test_ml_summary_requires_concrete_performance_interpretation_without_what_if():
    facts = SummaryFacts.model_validate({
        "executionType": "ML", "language": "en", "rowCount": 149980,
        "objective": "Estimate expected call charge",
        "algorithm": "XGBOOST_REGRESSOR", "target": "charge_amount",
        "features": ["duration_seconds", "call_type"],
        "drivers": [
            {"feature": "duration_seconds", "importance": 349},
            {"feature": "call_type: VOICE", "importance": 1},
        ],
        "facts": [
            {"code": "RMSE", "value": 0.562293},
            {"code": "MAE", "value": 0.25142},
            {"code": "R2", "value": 0.993938},
        ],
        "warnings": [],
    })
    generic = (
        "The model demonstrates high reliability and can support business decisions. "
        "Call duration is the strongest influence."
    )

    assert ResultExplainer._ml_specificity_violations(generic, facts)
    grounded = ResultExplainer._grounded_management_fallback(facts)
    assert "0.25" in grounded
    assert "99.39% of observed variation" in grounded
    assert "duration seconds" in grounded
    assert "what-if" not in grounded.lower()


def test_zero_row_result_rejects_invented_comparison_and_guides_no_data_summary():
    facts = SummaryFacts.model_validate({
        "executionType": "REPORT", "language": "en", "rowCount": 0,
        "objective": "Compare sales by category", "facts": [], "warnings": [],
    })
    invented = "The breakdown provides a clear comparison across product categories."

    assert ResultExplainer._zero_result_violations(invented, facts)
    grounded = ResultExplainer._grounded_management_fallback(facts)
    assert "No data matched this request" in grounded
    assert ResultExplainer._zero_result_violations(grounded, facts) == []
