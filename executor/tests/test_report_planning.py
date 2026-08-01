import asyncio
from uuid import uuid4

import pytest
from pydantic import ValidationError

from kozmik_executor.chat.providers import DeterministicMockProvider
from kozmik_executor.planning.api import _generate_report_order
from kozmik_executor.planning.models import ReportOrder, ReportPlanningRequest
from kozmik_executor.planning.prompts import SYSTEM_PROMPT, build_prompt
from kozmik_executor.planning.validation import PlanningValidationError, validate_order


def request() -> ReportPlanningRequest:
    return ReportPlanningRequest.model_validate({
        "schemaVersion": "1.0", "requestId": str(uuid4()), "correlationId": "test",
        "actorUserId": str(uuid4()), "capabilities": ["REPORTER"],
        "userRequest": "Count orders", "requestedLanguage": "en",
        "authorizedSchema": {
            "entityId": str(uuid4()),
            "columns": [
                {"columnName": "amount", "businessName": "Amount", "dataType": "DECIMAL",

},
                {"columnName": "category", "businessName": "Category", "dataType": "STRING",

},
                {"columnName": "sale_date", "businessName": "Sale date", "dataType": "DATE",

},
                {"columnName": "secret", "businessName": "Secret", "dataType": "STRING",

},
            ],
        },
    })


def test_mock_generates_valid_authorized_order():
    planning_request = request()
    raw = asyncio.run(DeterministicMockProvider().complete_json(
        SYSTEM_PROMPT, build_prompt(planning_request)))
    order = ReportOrder.model_validate(raw)
    validate_order(order, planning_request)
    assert order.payload.select[0].column == "amount"


def test_validation_feedback_regenerates_malformed_array_fields():
    planning_request = request()
    valid = asyncio.run(DeterministicMockProvider().complete_json(
        SYSTEM_PROMPT, build_prompt(planning_request)))

    class CorrectingProvider:
        calls = 0

        async def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
            self.calls += 1
            if self.calls == 1:
                return {**valid, "payload": {**valid["payload"], "select": {"column": "amount"}}}
            assert "payload.select" in user_prompt
            assert "Array fields must always be JSON arrays" in user_prompt
            return valid

    provider = CorrectingProvider()
    order = asyncio.run(_generate_report_order(provider, planning_request))

    assert provider.calls == 2
    assert order.payload.select[0].column == "amount"


def test_categorical_business_wording_is_regenerated_to_an_approved_value():
    planning_request = request()
    category = planning_request.authorized_schema.columns[1].model_copy(update={
        "categorical_values": ["STORE", "WEB", "PARTNER"],
    })
    planning_request.authorized_schema.columns[1] = category
    entity_id = str(planning_request.authorized_schema.entity_id)

    def report(value: str) -> dict:
        return {
            "schemaVersion": "1.0", "executionType": "REPORT",
            "entityId": entity_id, "requestedLanguage": "en",
            "requestSummary": "Online category totals",
            "constraints": {"maxPreviewRows": 10, "timeoutSeconds": 60},
            "payload": {
                "select": [{"column": "category"}],
                "filters": [{"column": "category", "operator": "EQ", "value": value}],
                "groupBy": [], "temporalGroupBy": [], "aggregations": [],
                "orderBy": [], "limit": 100, "chartHints": [],
            },
        }

    class Provider:
        calls = 0

        async def complete_json(self, _system_prompt: str, user_prompt: str) -> dict:
            self.calls += 1
            if self.calls == 1:
                return report("Online")
            assert "Approved values: STORE, WEB, PARTNER" in user_prompt
            return report("WEB")

    provider = Provider()
    order = asyncio.run(_generate_report_order(provider, planning_request))

    assert provider.calls == 2
    assert order.payload.filters[0].value == "WEB"
    assert order.constraints.max_preview_rows == 100
    assert order.constraints.timeout_seconds == 7200


def test_monthly_report_normalizes_bounded_date_filter_and_validates():
    planning_request = request()
    raw = {
        "schemaVersion": "1.0", "executionType": "REPORT",
        "entityId": str(planning_request.authorized_schema.entity_id),

        "requestedLanguage": "en", "requestSummary": "Monthly net sales",
        "constraints": {"maxPreviewRows": 100, "timeoutSeconds": 60},
        "payload": {
            "select": [{"column": "sale_date", "alias": "sales_month"}],
            "filters": [{
                "column": "sale_date", "operator": "BETWEEN",
                "value": {"start": "2026-01-01", "end": "2026-06-30"},
            }],
            "groupBy": [],
            "temporalGroupBy": [{
                "column": "sale_date", "granularity": "MONTH", "alias": "sales_month",
            }],
            "aggregations": [{
                "function": "SUM", "column": "amount", "alias": "total_net_sales",
            }],
            "orderBy": [{"column": "sales_month", "direction": "ASC"}],
            "limit": 100,
            "chartHints": [{
                "chartType": "LINE", "categoryColumn": "sales_month",
                "valueColumn": "total_net_sales",
            }],
        },
    }

    class Provider:
        async def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
            return raw

    order = asyncio.run(_generate_report_order(Provider(), planning_request))

    assert order.payload.filters[0].values == ["2026-01-01", "2026-06-30"]
    assert order.payload.temporal_group_by[0].granularity.value == "MONTH"


def test_monthly_report_normalizes_invented_month_alias():
    planning_request = request().model_copy(update={
        "user_request": (
            "Show monthly total net sales from January through December 2026, "
            "ordered chronologically. Include a line chart."
        ),
    })
    raw = {
        "schemaVersion": "1.0", "executionType": "REPORT",
        "entityId": str(planning_request.authorized_schema.entity_id),
        "requestedLanguage": "en", "requestSummary": "Monthly net sales",
        "constraints": {"maxPreviewRows": 100, "timeoutSeconds": 60},
        "payload": {
            "select": [{"column": "sales_month", "displayLabel": "Sales month"}],
            "filters": [{
                "column": "sale_date", "operator": "BETWEEN",
                "values": ["2026-01-01", "2026-12-31"],
            }],
            "groupBy": ["sales_month"],
            "temporalGroupBy": [],
            "aggregations": [{
                "function": "SUM", "column": "amount", "alias": "total_net_sales",
            }],
            "orderBy": [{"column": "sales_month", "direction": "ASC"}],
            "limit": 100,
            "chartHints": [{
                "chartType": "LINE", "categoryColumn": "sales_month",
                "valueColumn": "total_net_sales",
            }],
        },
    }

    class Provider:
        async def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
            return raw

    order = asyncio.run(_generate_report_order(Provider(), planning_request))

    assert order.payload.group_by == []
    assert order.payload.select[0].column == "sale_date"
    assert order.payload.select[0].alias == "sales_month"
    assert order.payload.temporal_group_by[0].column == "sale_date"
    assert order.payload.temporal_group_by[0].granularity.value == "MONTH"
    assert order.payload.temporal_group_by[0].display_label == "Sales Month"
    assert order.payload.select[0].display_label == "Sales Month"
    assert order.payload.temporal_group_by[0].alias == "sales_month"


def test_monthly_report_removes_redundant_daily_group_and_exposes_month_alias():
    planning_request = request()
    raw = {
        "schemaVersion": "1.0", "executionType": "REPORT",
        "entityId": str(planning_request.authorized_schema.entity_id),
        "requestedLanguage": "en", "requestSummary": "Monthly net sales",
        "constraints": {"maxPreviewRows": 100, "timeoutSeconds": 60},
        "payload": {
            "select": [{
                "column": "sale_date", "alias": "sale_date",
                "displayLabel": "Sale Date",
            }],
            "filters": [], "groupBy": ["sale_date", "month"],
            "temporalGroupBy": [{
                "column": "sale_date", "granularity": "MONTH", "alias": "month",
                "displayLabel": "Month",
            }],
            "aggregations": [{
                "function": "SUM", "column": "amount", "alias": "total_net_sales",
            }],
            "orderBy": [{"column": "month", "direction": "ASC"}],
            "limit": 100,
            "chartHints": [{
                "chartType": "LINE", "categoryColumn": "month",
                "valueColumn": "total_net_sales",
            }],
        },
    }

    class Provider:
        async def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
            return raw

    order = asyncio.run(_generate_report_order(Provider(), planning_request))

    assert order.payload.group_by == []
    assert order.payload.select[0].column == "sale_date"
    assert order.payload.select[0].alias == "month"
    assert order.payload.select[0].display_label == "Month"


def test_report_resolves_selected_group_alias_to_authorized_source_column():
    planning_request = request()
    raw = {
        "schemaVersion": "1.0", "executionType": "REPORT",
        "entityId": str(planning_request.authorized_schema.entity_id),
        "requestedLanguage": "en", "requestSummary": "Totals by category",
        "constraints": {"maxPreviewRows": 100, "timeoutSeconds": 60},
        "payload": {
            "select": [{
                "column": "category", "alias": "category_name",
                "displayLabel": "Category",
            }],
            "filters": [], "groupBy": ["category_name"],
            "temporalGroupBy": [],
            "aggregations": [{
                "function": "SUM", "column": "amount", "alias": "total_amount",
            }],
            "orderBy": [], "limit": 100, "chartHints": [],
        },
    }

    class Provider:
        async def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
            return raw

    order = asyncio.run(_generate_report_order(Provider(), planning_request))

    assert order.payload.group_by == ["category"]


def test_turkish_presentation_aliases_are_normalized_without_changing_columns():
    planning_request = request()
    raw = {
        "schemaVersion": "1.0", "executionType": "REPORT",
        "entityId": str(planning_request.authorized_schema.entity_id),
        "requestedLanguage": "tr", "requestSummary": "Kategori bazlı toplamlar",
        "constraints": {"maxPreviewRows": 100, "timeoutSeconds": 60},
        "payload": {
            "select": [{
                "column": "category", "alias": "Ürün Kategorisi",
            }],
            "filters": [], "groupBy": ["Ürün Kategorisi"],
            "temporalGroupBy": [],
            "aggregations": [{
                "function": "SUM", "column": "amount", "alias": "Toplam Tutar",
            }],
            "having": {
                "type": "CONDITION", "column": "Toplam Tutar",
                "operator": "GT", "value": 0,
            },
            "orderBy": [{"column": "Toplam Tutar", "direction": "DESC"}],
            "limit": 100,
            "chartHints": [{
                "chartType": "BAR", "categoryColumn": "Ürün Kategorisi",
                "valueColumn": "Toplam Tutar",
            }],
        },
    }

    class Provider:
        async def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
            return raw

    order = asyncio.run(_generate_report_order(Provider(), planning_request))

    assert order.payload.select[0].column == "category"
    assert order.payload.select[0].alias == "urun_kategorisi"
    assert order.payload.select[0].display_label == "Ürün Kategorisi"
    assert order.payload.group_by == ["category"]
    assert order.payload.aggregations[0].alias == "toplam_tutar"
    assert order.payload.aggregations[0].display_label == "Toplam Tutar"
    assert order.payload.having.column == "toplam_tutar"
    assert order.payload.order_by[0].column == "toplam_tutar"
    assert order.payload.chart_hints[0].category_column == "urun_kategorisi"
    assert order.payload.chart_hints[0].value_column == "toplam_tutar"


def test_temporal_grouping_rejects_non_temporal_column():
    planning_request = request()
    raw = {
        "schemaVersion": "1.0", "executionType": "REPORT",
        "entityId": str(planning_request.authorized_schema.entity_id),

        "requestedLanguage": "en", "requestSummary": "Invalid month",
        "constraints": {"maxPreviewRows": 100, "timeoutSeconds": 60},
        "payload": {
            "select": [{"column": "category", "alias": "sales_month"}],
            "filters": [], "groupBy": [],
            "temporalGroupBy": [{
                "column": "category", "granularity": "MONTH", "alias": "sales_month",
            }],
            "aggregations": [{"function": "COUNT", "alias": "row_count"}],
            "orderBy": [], "limit": 100, "chartHints": [],
        },
    }

    with pytest.raises(PlanningValidationError) as error:
        validate_order(ReportOrder.model_validate(raw), planning_request)

    assert any(
        issue.code == "TEMPORAL_GROUP_TYPE_MISMATCH" for issue in error.value.issues
    )


def test_rejects_unknown_columns():
    planning_request = request()
    base = {
        "schemaVersion": "1.0", "executionType": "REPORT",
        "entityId": str(planning_request.authorized_schema.entity_id),

        "requestedLanguage": "en", "requestSummary": "Invalid",
        "constraints": {"maxPreviewRows": 100, "timeoutSeconds": 60},
        "payload": {"select": [{"column": "not_in_schema"}], "filters": [], "groupBy": [],
                    "aggregations": [], "orderBy": [], "limit": 10, "chartHints": []},
    }
    with pytest.raises(PlanningValidationError) as error:
        validate_order(ReportOrder.model_validate(base), planning_request)
    assert error.value.issues[0].code == "COLUMN_NOT_AUTHORIZED"


def test_schema_forbids_arbitrary_sql():
    planning_request = request()
    invalid = {
        "schemaVersion": "1.0", "executionType": "REPORT",
        "entityId": str(planning_request.authorized_schema.entity_id),

        "requestedLanguage": "en", "requestSummary": "Unsafe",
        "constraints": {"maxPreviewRows": 100, "timeoutSeconds": 60},
        "payload": {"select": [{"column": "amount"}], "filters": [], "groupBy": [],
                    "aggregations": [], "orderBy": [], "limit": 10, "chartHints": [],
                    "sql": "select * from orders"},
    }
    with pytest.raises(ValidationError):
        ReportOrder.model_validate(invalid)
    schema = ReportOrder.model_json_schema(by_alias=True)
    assert schema["additionalProperties"] is False


def test_prompt_contains_metadata_not_business_rows():
    prompt = build_prompt(request())
    assert "columnName" in prompt
    assert "raw business rows" in SYSTEM_PROMPT
    assert "Never emit SQL" in SYSTEM_PROMPT
    assert "recent rows as row-level" in SYSTEM_PROMPT
    assert "net_amount" in SYSTEM_PROMPT


def test_aggregation_aliases_are_valid_governed_order_and_chart_fields():
    planning_request = request()
    order = ReportOrder.model_validate({
        "schemaVersion": "1.0", "executionType": "REPORT",
        "entityId": str(planning_request.authorized_schema.entity_id),

        "requestedLanguage": "en", "requestSummary": "Total amount",
        "constraints": {"maxPreviewRows": 100, "timeoutSeconds": 60},
        "payload": {
            "select": [{"column": "amount", "alias": "amount"}],
            "filters": [], "groupBy": [],
            "aggregations": [{"function": "SUM", "column": "amount",
                              "alias": "total_amount"}],
            "orderBy": [{"column": "total_amount", "direction": "DESC"}],
            "limit": 10,
            "chartHints": [{"chartType": "BAR", "valueColumn": "total_amount"}],
        },
    })
    validate_order(order, planning_request)


def test_aggregate_report_rejects_selected_field_when_group_by_is_empty():
    planning_request = request()
    order = ReportOrder.model_validate({
        "schemaVersion": "1.0", "executionType": "REPORT",
        "entityId": str(planning_request.authorized_schema.entity_id),

        "requestedLanguage": "en",
        "requestSummary": "Show total sales and product category without grouping",
        "constraints": {"maxPreviewRows": 100, "timeoutSeconds": 60},
        "payload": {
            "select": [{"column": "category", "alias": "category"}],
            "filters": [], "groupBy": [],
            "aggregations": [{"function": "SUM", "column": "amount",
                              "alias": "total_amount"}],
            "orderBy": [], "limit": 1, "chartHints": [],
        },
    })

    with pytest.raises(PlanningValidationError) as error:
        validate_order(order, planning_request)

    assert any(issue.code == "SELECT_FIELD_NOT_GROUPED" for issue in error.value.issues)


def test_having_may_only_reference_grouped_outputs_or_aggregation_aliases():
    planning_request = request()
    order = ReportOrder.model_validate({
        "schemaVersion": "1.0", "executionType": "REPORT",
        "entityId": str(planning_request.authorized_schema.entity_id),

        "requestedLanguage": "en", "requestSummary": "Invalid having",
        "constraints": {"maxPreviewRows": 100, "timeoutSeconds": 60},
        "payload": {
            "select": [{"column": "amount"}], "filters": [], "groupBy": ["amount"],
            "aggregations": [{"function": "COUNT", "alias": "row_count"}],
            "having": {"type": "CONDITION", "column": "not_an_output",
                       "operator": "GT", "value": 1},
            "orderBy": [], "limit": 10, "chartHints": [],
        },
    })
    with pytest.raises(PlanningValidationError) as error:
        validate_order(order, planning_request)
    assert any(issue.code == "HAVING_FIELD_NOT_AVAILABLE" for issue in error.value.issues)
