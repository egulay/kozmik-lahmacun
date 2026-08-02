import asyncio
import shutil
from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from pyspark.sql import SparkSession

from kozmik_executor.execution.spark_report import SparkReportExecutor
from kozmik_executor.planning.models import ReportOrder


class RecordingMinio:
    def __init__(self):
        self.upload = None

    def fput_object(self, bucket, object_key, path):
        self.upload = (bucket, object_key, path)


@pytest.fixture(scope="module")
def spark():
    session = (SparkSession.builder.master("local[2]").appName("kozmik-report-test")
               .config("spark.ui.enabled", "false")
               .config("spark.sql.session.timeZone", "UTC").getOrCreate())
    yield session
    session.stop()


def test_trusted_registry_executes_deterministic_dataset_and_writes_parquet(tmp_path, spark):
    source = tmp_path / "sales.json"
    source.write_text(
        "\n".join([
            '{"region":"TR","amount":10}',
            '{"region":"TR","amount":20}',
            '{"region":"DE","amount":7}',
        ]),
        encoding="utf-8",
    )
    entity_id, execution_id = uuid4(), uuid4()
    order = ReportOrder.model_validate({
        "schemaVersion": "1.0", "executionType": "REPORT",
        "entityId": str(entity_id),
        "requestedLanguage": "en", "requestSummary": "Sales by region",
        "constraints": {"maxPreviewRows": 1, "timeoutSeconds": 30},
        "payload": {
            "select": [{"column": "region", "displayLabel": "Bölge"}],
            "filters": [], "groupBy": ["region"],
            "aggregations": [{"function": "SUM", "column": "amount",
                              "alias": "total_amount", "displayLabel": "Toplam satış"}],
            "orderBy": [{"column": "total_amount", "direction": "DESC"}],
            "limit": 100,
            "chartHints": [{"chartType": "BAR", "categoryColumn": "region",
                            "valueColumn": "total_amount"}],
        },
    })
    minio = RecordingMinio()
    result = asyncio.run(SparkReportExecutor(spark, minio).execute(
        execution_id, order,
        {"datasetUri": str(source), "datasetFormat": "json", "timeoutSeconds": 30},
        asyncio.Event(),
    ))
    assert result["rowCount"] == 2
    assert result["preview"]["rows"] == [{"region": "TR", "total_amount": 30}]
    assert result["preview"]["columns"][0]["label"] == "Bölge"
    assert result["preview"]["columns"][1]["label"] == "Toplam satış"
    assert result["preview"]["truncated"] is True
    assert result["kpis"] == []
    assert result["charts"][0]["type"] == "BAR"
    assert result["charts"][0]["title"] == "Toplam satış"
    assert result["charts"][0]["valueField"] == "total_amount"
    assert result["charts"][0]["valueLabel"] == "Toplam satış"
    assert result["charts"][0]["categoryLabel"] == "Bölge"
    assert result["charts"][0]["categories"] == ["TR", "DE"]
    assert result["charts"][0]["series"][0]["data"] == [30, 7]
    assert result["summaryFacts"]["reportBreakdown"] == [
        {"region": "TR", "total_amount": 30,
         "total_amountShareOfTotalPercent": pytest.approx(81.081081)},
        {"region": "DE", "total_amount": 7,
         "total_amountShareOfTotalPercent": pytest.approx(18.918919)},
    ]
    comparison = result["summaryFacts"]["reportComparisons"][0]
    assert result["summaryFacts"]["schemaVersion"] == "2.0"
    assert comparison["highest"] == {"dimensions": {"region": "TR"}, "value": 30}
    assert comparison["lowest"] == {"dimensions": {"region": "DE"}, "value": 7}
    assert comparison["absoluteSpread"] == 23
    assert comparison["relativeSpread"]["method"] == "SYMMETRIC_PERCENT_DIFFERENCE"
    assert comparison["relativeSpread"]["percent"] == pytest.approx(124.3243, rel=1e-4)
    assert comparison["relativeSpread"]["meaning"] == (
        "RELATIVE_SPREAD_BETWEEN_HIGHEST_AND_LOWEST"
    )
    assert comparison["highestTieCount"] == 1
    assert comparison["lowestTieCount"] == 1
    assert comparison["groupCount"] == 2
    assert minio.upload[0] == "results"
    assert minio.upload[1].startswith(f"executions/{execution_id}/")
    assert shutil.which("java") is not None


def test_summary_breakdown_excludes_sensitive_grouping_fields():
    order = ReportOrder.model_validate({
        "schemaVersion": "1.0", "executionType": "REPORT",
        "entityId": str(uuid4()), "requestedLanguage": "en",
        "requestSummary": "Aggregate by subscriber and type",
        "constraints": {"maxPreviewRows": 20, "timeoutSeconds": 30},
        "payload": {
            "select": [{"column": "subscriber_id"}, {"column": "call_type"}],
            "filters": [], "groupBy": ["subscriber_id", "call_type"],
            "aggregations": [{"function": "COUNT", "column": None,
                              "alias": "call_count"}],
            "orderBy": [], "limit": 100, "chartHints": [],
        },
    })

    breakdown = SparkReportExecutor._report_breakdown(order, [{
        "subscriber_id": "SECRET-42", "call_type": "VOICE", "call_count": 4,
    }])

    assert breakdown == [{
        "call_type": "VOICE", "call_count": 4,
        "call_countShareOfTotalPercent": 100.0,
    }]


def test_nested_boolean_filters_having_and_multiple_order_fields(spark):
    frame = spark.createDataFrame([
        ("TR", "mobile", 80),
        ("TR", "fiber", 30),
        ("TR", "legacy", 500),
        ("DE", "mobile", 70),
        ("DE", "fiber", 10),
        ("FR", "mobile", 200),
    ], ["region", "channel", "amount"])
    order = ReportOrder.model_validate({
        "schemaVersion": "1.0", "executionType": "REPORT",
        "entityId": str(uuid4()),
        "requestedLanguage": "en", "requestSummary": "Complex grouped report",
        "constraints": {"maxPreviewRows": 100, "timeoutSeconds": 30},
        "payload": {
            "select": [{"column": "region", "alias": "market"}],
            "filters": {
                "type": "GROUP", "operator": "AND", "children": [
                    {"type": "GROUP", "operator": "OR", "children": [
                        {"type": "CONDITION", "column": "channel",
                         "operator": "EQ", "value": "mobile"},
                        {"type": "CONDITION", "column": "channel",
                         "operator": "EQ", "value": "fiber"},
                    ]},
                    {"type": "CONDITION", "column": "amount",
                     "operator": "GTE", "value": 20},
                ],
            },
            "groupBy": ["region"],
            "aggregations": [
                {"function": "SUM", "column": "amount", "alias": "total_amount"},
                {"function": "COUNT", "alias": "row_count"},
            ],
            "having": {
                "type": "GROUP", "operator": "AND", "children": [
                    {"type": "CONDITION", "column": "total_amount",
                     "operator": "GT", "value": 75},
                    {"type": "CONDITION", "column": "row_count",
                     "operator": "GTE", "value": 1},
                ],
            },
            "orderBy": [
                {"column": "total_amount", "direction": "DESC"},
                {"column": "market", "direction": "ASC"},
            ],
            "limit": 100, "chartHints": [],
        },
    })

    rows = [row.asDict() for row in SparkReportExecutor.map_order(frame, order).collect()]

    assert rows == [
        {"market": "FR", "total_amount": 200, "row_count": 1},
        {"market": "TR", "total_amount": 110, "row_count": 2},
    ]

    mapped = SparkReportExecutor.map_order(frame, order)
    normalized = SparkReportExecutor._normalized_comparisons(
        mapped, order, mapped.count()
    )
    assert normalized[0]["numeratorMeasure"] == "total_amount"
    assert normalized[0]["denominatorMeasure"] == "row_count"
    assert normalized[0]["highest"] == {
        "dimensions": {"market": "FR"}, "value": 200,
    }
    assert normalized[0]["lowest"] == {
        "dimensions": {"market": "TR"}, "value": 55,
    }


def test_time_change_uses_complete_additive_period_totals(spark):
    frame = spark.createDataFrame([
        (date(2030, 1, 1), "A", 40, 4),
        (date(2030, 1, 1), "B", 60, 6),
        (date(2030, 2, 1), "A", 70, 7),
        (date(2030, 2, 1), "B", 40, 4),
    ], ["period", "group_alpha", "measured_amount", "record_count"])
    order = ReportOrder.model_validate({
        "schemaVersion": "1.0", "executionType": "REPORT",
        "entityId": str(uuid4()), "requestedLanguage": "en",
        "requestSummary": "Compare neutral measures over time.",
        "constraints": {"maxPreviewRows": 100, "timeoutSeconds": 30},
        "payload": {
            "select": [
                {"column": "event_time", "alias": "period"},
                {"column": "group_alpha"},
            ],
            "filters": [], "groupBy": ["group_alpha"],
            "temporalGroupBy": [{
                "column": "event_time", "alias": "period", "granularity": "MONTH",
            }],
            "aggregations": [
                {"function": "SUM", "column": "measure_beta", "alias": "measured_amount"},
                {"function": "COUNT", "alias": "record_count"},
            ],
            "orderBy": [], "limit": 100, "chartHints": [],
        },
    })

    changes = SparkReportExecutor._time_changes(frame, order, frame.count())

    assert changes[0]["measure"] == "measured_amount"
    assert changes[0]["earlier"] == {
        "dimensions": {"period": "2030-01-01"}, "value": 100,
    }
    assert changes[0]["later"] == {
        "dimensions": {"period": "2030-02-01"}, "value": 110,
    }
    assert changes[0]["absoluteChange"] == 10
    assert changes[0]["percentageChange"] == 10


def test_share_of_total_is_not_fabricated_for_non_additive_aggregations(spark):
    frame = spark.createDataFrame([
        ("Group A", 40.0), ("Group B", 20.0),
    ], ["group_alpha", "average_measure"])
    order = ReportOrder.model_validate({
        "schemaVersion": "1.0", "executionType": "REPORT",
        "entityId": str(uuid4()), "requestedLanguage": "en",
        "requestSummary": "Compare a neutral average by group.",
        "constraints": {"maxPreviewRows": 100, "timeoutSeconds": 30},
        "payload": {
            "select": [{"column": "group_alpha"}],
            "filters": [], "groupBy": ["group_alpha"],
            "aggregations": [{
                "function": "AVG", "column": "measure_beta", "alias": "average_measure",
            }],
            "orderBy": [], "limit": 100, "chartHints": [],
        },
    })

    comparison = SparkReportExecutor._summary_comparisons(
        frame, order, frame.count(),
    )[0]

    assert comparison["highest"] == {
        "dimensions": {"group_alpha": "Group A"}, "value": 40,
    }
    assert comparison["highestShareOfTotalPercent"] is None


def test_grouped_bar_chart_uses_second_grouping_dimension_as_series():
    order = ReportOrder.model_validate({
        "schemaVersion": "1.0", "executionType": "REPORT",
        "entityId": str(uuid4()),
        "requestedLanguage": "en", "requestSummary": "Sales by region and channel",
        "constraints": {"maxPreviewRows": 100, "timeoutSeconds": 30},
        "payload": {
            "select": [{"column": "region"}, {"column": "channel"}],
            "filters": [], "groupBy": ["region", "channel"],
            "aggregations": [{
                "function": "SUM", "column": "net_amount", "alias": "total_net_sales",
            }],
            "orderBy": [{"column": "region", "direction": "ASC"}],
            "limit": 100,
            "chartHints": [{
                "chartType": "BAR", "categoryColumn": "region",
                "valueColumn": "total_net_sales",
            }],
        },
    })
    rows = [
        {"region": "Ege", "channel": "WEB", "total_net_sales": 10},
        {"region": "Ege", "channel": "STORE", "total_net_sales": 20},
        {"region": "Marmara", "channel": "WEB", "total_net_sales": 30},
        {"region": "Marmara", "channel": "STORE", "total_net_sales": 40},
    ]

    chart = SparkReportExecutor._charts(order, rows)[0]

    assert chart["categories"] == ["Ege", "Marmara"]
    assert chart["title"] == "Total Net Sales"
    assert chart["categoryLabel"] == "Region"
    assert chart["seriesLabel"] == "Channel"
    assert chart["seriesField"] == "channel"
    assert chart["series"] == [
        {"name": "WEB", "data": [10, 30]},
        {"name": "STORE", "data": [20, 40]},
    ]


def test_charts_aggregate_dimensions_not_displayed_by_the_chart():
    order = ReportOrder.model_validate({
        "schemaVersion": "1.0", "executionType": "REPORT",
        "entityId": str(uuid4()), "requestedLanguage": "en",
        "requestSummary": "Calls by month, type, and region",
        "constraints": {"maxPreviewRows": 100, "timeoutSeconds": 30},
        "payload": {
            "select": [
                {"column": "month"}, {"column": "call_type"}, {"column": "region"},
            ],
            "filters": [], "groupBy": ["month", "call_type", "region"],
            "aggregations": [{"function": "COUNT", "alias": "total_calls"}],
            "orderBy": [], "limit": 100,
            "chartHints": [
                {"chartType": "LINE", "categoryColumn": "month",
                 "valueColumn": "total_calls"},
                {"chartType": "PIE", "categoryColumn": "call_type",
                 "valueColumn": "total_calls"},
            ],
        },
    })
    rows = [
        {"month": "Jan", "call_type": "VOICE", "region": "Ege", "total_calls": 10},
        {"month": "Jan", "call_type": "VOICE", "region": "Marmara", "total_calls": 20},
        {"month": "Jan", "call_type": "SMS", "region": "Ege", "total_calls": 5},
        {"month": "Feb", "call_type": "VOICE", "region": "Ege", "total_calls": 7},
        {"month": "Feb", "call_type": "SMS", "region": "Ege", "total_calls": 3},
    ]

    line, pie = SparkReportExecutor._charts(order, rows)

    assert line["series"] == [
        {"name": "VOICE", "data": [30, 7]},
        {"name": "SMS", "data": [5, 3]},
    ]
    assert pie["categories"] == ["VOICE", "SMS"]
    assert pie["series"][0]["data"] == [37, 8]


def test_natural_language_string_filters_are_case_insensitive(spark):
    frame = spark.createDataFrame([
        ("Marmara", "ONLINE", 5, 100),
        ("Ege", "online", 3, 80),
        ("Akdeniz", "STORE", 4, 70),
    ], ["region", "channel", "quantity", "net_amount"])
    order = ReportOrder.model_validate({
        "schemaVersion": "1.0", "executionType": "REPORT",
        "entityId": str(uuid4()),
        "requestedLanguage": "en", "requestSummary": "Online sales",
        "constraints": {"maxPreviewRows": 100, "timeoutSeconds": 30},
        "payload": {
            "select": [{"column": "region"}],
            "filters": {
                "type": "GROUP", "operator": "AND", "children": [
                    {"type": "CONDITION", "column": "region", "operator": "IN",
                     "values": ["marmara", "EGE"]},
                    {"type": "CONDITION", "column": "channel", "operator": "EQ",
                     "value": "Online"},
                    {"type": "CONDITION", "column": "quantity", "operator": "GTE",
                     "value": 2},
                ],
            },
            "groupBy": ["region"],
            "aggregations": [
                {"function": "SUM", "column": "net_amount", "alias": "total_net_sales"},
            ],
            "orderBy": [{"column": "total_net_sales", "direction": "DESC"}],
            "limit": 100, "chartHints": [],
        },
    })

    rows = [row.asDict() for row in SparkReportExecutor.map_order(frame, order).collect()]

    assert rows == [
        {"region": "Marmara", "total_net_sales": 100},
        {"region": "Ege", "total_net_sales": 80},
    ]


def test_monthly_date_bucket_and_bounded_range_are_mapped_without_sql(spark):
    frame = spark.createDataFrame([
        (date(2025, 12, 31), 999),
        (date(2026, 1, 2), 100),
        (date(2026, 1, 20), 50),
        (date(2026, 2, 1), 70),
        (date(2026, 6, 30), 30),
        (date(2026, 7, 1), 999),
    ], ["sale_date", "net_amount"])
    order = ReportOrder.model_validate({
        "schemaVersion": "1.0", "executionType": "REPORT",
        "entityId": str(uuid4()),
        "requestedLanguage": "en", "requestSummary": "Monthly sales",
        "constraints": {"maxPreviewRows": 100, "timeoutSeconds": 30},
        "payload": {
            "select": [{"column": "sale_date", "alias": "sales_month"}],
            "filters": [{
                "column": "sale_date", "operator": "BETWEEN",
                "values": ["2026-01-01", "2026-06-30"],
            }],
            "groupBy": [],
            "temporalGroupBy": [{
                "column": "sale_date", "granularity": "MONTH", "alias": "sales_month",
            }],
            "aggregations": [{
                "function": "SUM", "column": "net_amount", "alias": "total_net_sales",
            }],
            "orderBy": [{"column": "sales_month", "direction": "ASC"}],
            "limit": 100, "chartHints": [],
        },
    })

    rows = [row.asDict() for row in SparkReportExecutor.map_order(frame, order).collect()]

    assert [(row["sales_month"].month, row["total_net_sales"]) for row in rows] == [
        (1, 150),
        (2, 70),
        (6, 30),
    ]


def test_utc_timestamp_boundaries_are_deterministic(spark):
    frame = spark.createDataFrame([
        (datetime(2026, 6, 30, 23, 59, 59, tzinfo=timezone.utc), 10),
        (datetime(2026, 7, 1, 0, 0, 0, tzinfo=timezone.utc), 999),
    ], ["event_time", "charge"])
    order = ReportOrder.model_validate({
        "schemaVersion": "1.0", "executionType": "REPORT",
        "entityId": str(uuid4()), "requestedLanguage": "en",
        "requestSummary": "June charge", "constraints": {
            "maxPreviewRows": 100, "timeoutSeconds": 30,
        },
        "payload": {
            "select": [{"column": "event_time", "alias": "month"}],
            "filters": [{
                "column": "event_time", "operator": "BETWEEN",
                "values": ["2026-06-01T00:00:00Z", "2026-06-30T23:59:59Z"],
            }],
            "groupBy": [], "temporalGroupBy": [{
                "column": "event_time", "granularity": "MONTH", "alias": "month",
            }],
            "aggregations": [{
                "function": "SUM", "column": "charge", "alias": "total_charge",
            }],
            "orderBy": [], "limit": 100, "chartHints": [],
        },
    })

    rows = [row.asDict() for row in SparkReportExecutor.map_order(frame, order).collect()]

    assert len(rows) == 1
    assert rows[0]["month"].month == 6
    assert rows[0]["total_charge"] == 10


def test_scalar_aggregate_facts_are_complete_result_only():
    order = ReportOrder.model_validate({
        "schemaVersion": "1.0", "executionType": "REPORT",
        "entityId": str(uuid4()), "requestedLanguage": "en",
        "requestSummary": "Total charge", "constraints": {
            "maxPreviewRows": 100, "timeoutSeconds": 30,
        },
        "payload": {
            "select": [{"column": "charge"}], "filters": [], "groupBy": [],
            "aggregations": [{
                "function": "SUM", "column": "charge", "alias": "total_charge",
            }],
            "orderBy": [], "limit": 100, "chartHints": [],
        },
    })

    assert SparkReportExecutor._report_measure_results(
        order, 1, [{"total_charge": 42}],
    ) == [{"measure": "total_charge", "value": 42}]
    assert SparkReportExecutor._report_measure_results(
        order, 2, [{"total_charge": 42}],
    ) == []
