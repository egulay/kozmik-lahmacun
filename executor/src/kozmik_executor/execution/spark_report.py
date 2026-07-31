import asyncio
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from minio import Minio
from pyspark.sql import DataFrame, SparkSession, functions as spark_fn

from kozmik_executor.planning.models import (
    AggregationFunction,
    FilterExpression,
    FilterItem,
    LogicalOperator,
    FilterOperator,
    ReportOrder,
    TemporalGranularity,
)
from kozmik_executor.spark_runtime import run_spark_operation

ARTIFACT_NAMESPACE = UUID("19af38da-8525-4e7f-986f-9cbb4fcc9ab8")


def _filter_eq(column, item):
    if isinstance(item.value, str):
        return spark_fn.lower(column.cast("string")) == item.value.casefold()
    return column == item.value


def _filter_ne(column, item):
    if isinstance(item.value, str):
        return spark_fn.lower(column.cast("string")) != item.value.casefold()
    return column != item.value


def _filter_in(column, item):
    if item.values and all(isinstance(value, str) for value in item.values):
        return spark_fn.lower(column.cast("string")).isin(
            [value.casefold() for value in item.values]
        )
    return column.isin(item.values)


def _filter_not_in(column, item):
    return ~_filter_in(column, item)


def _filter_contains(column, item):
    if isinstance(item.value, str):
        return spark_fn.lower(column.cast("string")).contains(item.value.casefold())
    return column.contains(str(item.value))


def _filter_starts_with(column, item):
    if isinstance(item.value, str):
        return spark_fn.lower(column.cast("string")).startswith(item.value.casefold())
    return column.startswith(str(item.value))


def _filter_ends_with(column, item):
    if isinstance(item.value, str):
        return spark_fn.lower(column.cast("string")).endswith(item.value.casefold())
    return column.endswith(str(item.value))


def _filter_between(column, item):
    return column.between(item.values[0], item.values[1])


FILTER_REGISTRY: dict[FilterOperator, Callable] = {
    FilterOperator.EQ: _filter_eq,
    FilterOperator.NE: _filter_ne,
    FilterOperator.GT: lambda c, i: c > i.value,
    FilterOperator.GTE: lambda c, i: c >= i.value,
    FilterOperator.LT: lambda c, i: c < i.value,
    FilterOperator.LTE: lambda c, i: c <= i.value,
    FilterOperator.IN: _filter_in,
    FilterOperator.NOT_IN: _filter_not_in,
    FilterOperator.BETWEEN: _filter_between,
    FilterOperator.CONTAINS: _filter_contains,
    FilterOperator.STARTS_WITH: _filter_starts_with,
    FilterOperator.ENDS_WITH: _filter_ends_with,
    FilterOperator.IS_NULL: lambda c, i: c.isNull(),
    FilterOperator.IS_NOT_NULL: lambda c, i: c.isNotNull(),
}

AGGREGATION_REGISTRY: dict[AggregationFunction, Callable] = {
    AggregationFunction.COUNT: lambda item: spark_fn.count(
        "*" if item.column is None else item.column
    ),
    AggregationFunction.COUNT_DISTINCT: lambda item: spark_fn.count_distinct(item.column),
    AggregationFunction.SUM: lambda item: spark_fn.sum(item.column),
    AggregationFunction.AVG: lambda item: spark_fn.avg(item.column),
    AggregationFunction.MIN: lambda item: spark_fn.min(item.column),
    AggregationFunction.MAX: lambda item: spark_fn.max(item.column),
}

TEMPORAL_GROUP_REGISTRY: dict[TemporalGranularity, Callable] = {
    TemporalGranularity.DAY: lambda column: spark_fn.date_trunc("day", column),
    TemporalGranularity.WEEK: lambda column: spark_fn.date_trunc("week", column),
    TemporalGranularity.MONTH: lambda column: spark_fn.date_trunc("month", column),
    TemporalGranularity.QUARTER: lambda column: spark_fn.date_trunc("quarter", column),
    TemporalGranularity.YEAR: lambda column: spark_fn.date_trunc("year", column),
}


class SparkReportExecutor:
    def __init__(self, spark: SparkSession | None = None, minio: Minio | None = None) -> None:
        self.spark = spark or (
            SparkSession.builder.appName("kozmik-report-worker")
            .config("spark.scheduler.mode", os.getenv("SPARK_SCHEDULER_MODE", "FAIR"))
            .getOrCreate()
        )
        self.minio = minio or Minio(
            os.getenv("MINIO_ENDPOINT", "localhost:9000"),
            access_key=os.getenv("MINIO_ACCESS_KEY", ""),
            secret_key=os.getenv("MINIO_SECRET_KEY", ""),
            secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
        )

    async def execute(
        self, execution_id: UUID, order: ReportOrder, configuration: dict[str, Any],
        cancelled: asyncio.Event,
    ) -> dict[str, Any]:
        configuration = configuration.get("execution", configuration)
        if cancelled.is_set():
            raise asyncio.CancelledError
        timeout = min(
            order.constraints.timeout_seconds,
            int(configuration.get("timeoutSeconds", order.constraints.timeout_seconds)),
        )
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(
                    run_spark_operation, "report-execution",
                    self._execute_sync, execution_id, order, configuration, cancelled),
                timeout=timeout,
            )
        except (asyncio.TimeoutError, asyncio.CancelledError):
            cancelled.set()
            self.spark.sparkContext.cancelJobGroup(str(execution_id))
            raise

    def cancel(self, execution_id: UUID) -> None:
        self.spark.sparkContext.cancelJobGroup(str(execution_id))

    def _execute_sync(
        self, execution_id: UUID, order: ReportOrder, configuration: dict[str, Any],
        cancelled: asyncio.Event,
    ) -> dict[str, Any]:
        dataset_uri = configuration.get("datasetUri")
        if not isinstance(dataset_uri, str) or not dataset_uri:
            raise ValueError("DATASET_URI_NOT_CONFIGURED")
        source_format = str(configuration.get("datasetFormat", "parquet")).lower()
        if source_format not in {"parquet", "json", "csv"}:
            raise ValueError("DATASET_FORMAT_NOT_ALLOWED")
        reader = self.spark.read
        if source_format == "csv":
            reader = reader.option("header", True).option("inferSchema", True)
        frame = reader.format(source_format).load(dataset_uri)
        transformed = self.map_order(frame, order)
        if cancelled.is_set():
            self.spark.sparkContext.cancelJobGroup(str(execution_id))
            raise asyncio.CancelledError
        self.spark.sparkContext.setJobGroup(str(execution_id), "Kozmik governed report", True)
        row_count = transformed.count()
        preview_limit = order.constraints.max_preview_rows
        preview_rows = [row.asDict(recursive=True) for row in transformed.limit(preview_limit).collect()]
        chart_rows = preview_rows
        if order.payload.aggregations and row_count > preview_limit:
            chart_limit = min(order.payload.limit, 1000)
            chart_rows = [
                row.asDict(recursive=True)
                for row in transformed.limit(chart_limit).collect()
            ]
        display_labels = self._display_labels(order)
        columns = [{"name": field.name, "type": field.dataType.simpleString().upper(),
                    "label": display_labels.get(field.name)}
                   for field in transformed.schema.fields]
        artifact_id = uuid5(ARTIFACT_NAMESPACE, str(execution_id))
        object_key = f"executions/{execution_id}/{artifact_id}.parquet"
        with tempfile.TemporaryDirectory(prefix="kozmik-result-") as directory:
            output = Path(directory) / "parquet"
            transformed.coalesce(1).write.mode("overwrite").parquet(str(output))
            part = next(output.glob("part-*.parquet"))
            self.minio.fput_object("results", object_key, str(part))
            size = part.stat().st_size
        return {
            "rowCount": row_count,
            "preview": {"columns": columns, "rows": preview_rows, "limit": preview_limit,
                        "truncated": row_count > preview_limit},
            "kpis": self._kpis(order, preview_rows),
            "charts": self._charts(order, chart_rows),
            "warnings": [],
            "artifact": {"artifactId": str(artifact_id), "format": "PARQUET",
                         "bucket": "results", "objectKey": object_key, "sizeBytes": size},
        }

    @staticmethod
    def _map_filter(expression: FilterExpression):
        if isinstance(expression, FilterItem):
            operation = FILTER_REGISTRY.get(expression.operator)
            if operation is None:
                raise ValueError("FILTER_OPERATOR_NOT_ALLOWED")
            return operation(spark_fn.col(expression.column), expression)
        mapped = [SparkReportExecutor._map_filter(child) for child in expression.children]
        combined = mapped[0]
        for child in mapped[1:]:
            combined = (
                combined & child
                if expression.operator == LogicalOperator.AND
                else combined | child
            )
        return combined

    @staticmethod
    def map_order(frame: DataFrame, order: ReportOrder) -> DataFrame:
        result = frame
        filters = order.payload.filters
        if isinstance(filters, list):
            for item in filters:
                result = result.filter(SparkReportExecutor._map_filter(item))
        else:
            result = result.filter(SparkReportExecutor._map_filter(filters))
        temporal_groups = {
            item.alias: item for item in order.payload.temporal_group_by
        }
        for item in order.payload.temporal_group_by:
            operation = TEMPORAL_GROUP_REGISTRY.get(item.granularity)
            if operation is None:
                raise ValueError("TEMPORAL_GRANULARITY_NOT_ALLOWED")
            result = result.withColumn(item.alias, operation(spark_fn.col(item.column)))
        aggregations = [
            AGGREGATION_REGISTRY[item.function](item).alias(item.alias)
            for item in order.payload.aggregations
        ]
        if aggregations:
            group_columns = [
                *order.payload.group_by,
                *(item.alias for item in order.payload.temporal_group_by),
            ]
            result = (result.groupBy(*group_columns).agg(*aggregations)
                      if group_columns else result.agg(*aggregations))
            if order.payload.having is not None:
                result = result.filter(SparkReportExecutor._map_filter(order.payload.having))
            grouped_selections = [
                spark_fn.col(
                    item.alias
                    if item.alias in temporal_groups
                    and temporal_groups[item.alias].column == item.column
                    else item.column
                ).alias(item.alias or item.column)
                for item in order.payload.select
                if item.column in order.payload.group_by
                or (
                    item.alias in temporal_groups
                    and temporal_groups[item.alias].column == item.column
                )
            ]
            result = result.select(
                *grouped_selections,
                *(spark_fn.col(item.alias) for item in order.payload.aggregations),
            )
        else:
            selections = [
                spark_fn.col(item.column).alias(item.alias or item.column)
                for item in order.payload.select
            ]
            result = result.select(*selections)
        if order.payload.order_by:
            result = result.orderBy(*[
                spark_fn.col(item.column).asc()
                if item.direction.value == "ASC" else spark_fn.col(item.column).desc()
                for item in order.payload.order_by
            ])
        return result.limit(order.payload.limit)

    @staticmethod
    def _kpis(order: ReportOrder, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not rows or order.payload.group_by or order.payload.temporal_group_by:
            return []
        return [
            {"code": item.alias.upper(), "labelKey": f"result.kpi.{item.alias}",
             "value": rows[0].get(item.alias), "unit": None}
            for item in order.payload.aggregations[:10]
            if item.alias in rows[0]
        ]

    @staticmethod
    def _display_labels(order: ReportOrder) -> dict[str, str]:
        labels = {
            item.alias or item.column: item.display_label
            for item in order.payload.select
            if item.display_label
        }
        labels.update({
            item.alias: item.display_label
            for item in order.payload.temporal_group_by
            if item.display_label
        })
        labels.update({
            item.alias: item.display_label
            for item in order.payload.aggregations
            if item.display_label
        })
        return labels

    @staticmethod
    def _charts(order: ReportOrder, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        charts = []
        grouped_dimensions = [
            *order.payload.group_by,
            *(item.alias for item in order.payload.temporal_group_by),
        ]
        for index, hint in enumerate(order.payload.chart_hints):
            category = hint.category_column
            value = hint.value_column
            if not category or not value:
                continue
            series_field = next(
                (
                    dimension for dimension in grouped_dimensions
                    if dimension != category
                    and any(row.get(dimension) is not None for row in rows)
                ),
                None,
            )
            categories = list(dict.fromkeys(
                row.get(category) for row in rows if row.get(category) is not None
            ))
            if hint.chart_type in {"BAR", "LINE"} and series_field:
                series_names = list(dict.fromkeys(
                    row.get(series_field) for row in rows
                    if row.get(series_field) is not None
                ))
                values: dict[tuple[Any, Any], Any] = {}
                for row in rows:
                    key = (row.get(category), row.get(series_field))
                    current = row.get(value)
                    if key[0] is None or key[1] is None or current is None:
                        continue
                    values[key] = values.get(key, 0) + current
                series = [
                    {
                        "name": name,
                        "data": [values.get((category_name, name))
                                 for category_name in categories],
                    }
                    for name in series_names
                ]
            else:
                values: dict[Any, Any] = {}
                for row in rows:
                    key = row.get(category)
                    current = row.get(value)
                    if key is None or current is None:
                        continue
                    values[key] = values.get(key, 0) + current
                series = [{
                    "name": value,
                    "data": [values.get(category_name) for category_name in categories],
                }]
            charts.append({
                "chartId": f"chart-{index + 1}",
                "type": hint.chart_type,
                "titleKey": "result.chart.report",
                "categoryField": category,
                "seriesField": series_field,
                "categories": categories,
                "series": series,
            })
        return charts
