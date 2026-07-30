import asyncio
import shutil
from datetime import date
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
               .config("spark.ui.enabled", "false").getOrCreate())
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
    assert result["kpis"][0]["value"] == 30
    assert result["charts"][0]["type"] == "BAR"
    assert result["charts"][0]["categories"] == ["TR"]
    assert result["charts"][0]["series"][0]["data"] == [30]
    assert minio.upload[0] == "results"
    assert minio.upload[1].startswith(f"executions/{execution_id}/")
    assert shutil.which("java") is not None


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
