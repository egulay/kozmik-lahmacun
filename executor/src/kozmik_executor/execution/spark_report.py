import asyncio
import math
import os
import re
import tempfile
from collections.abc import Callable
from decimal import Decimal
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from minio import Minio
from pyspark.sql import DataFrame, SparkSession, functions as spark_fn
from pyspark.sql.types import NumericType

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
from kozmik_executor.spark_session import build_spark_session

ARTIFACT_NAMESPACE = UUID("19af38da-8525-4e7f-986f-9cbb4fcc9ab8")
_SENSITIVE_SUMMARY_FIELD = re.compile(
    r"(?:^|_)(?:id|uuid|email|phone|mobile|address|name|subscriber|customer|account)(?:$|_)",
    re.IGNORECASE,
)


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
        self.spark = spark or build_spark_session("kozmik-report-worker")
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
        summary_comparisons = self._summary_comparisons(transformed, order, row_count)
        normalized_comparisons = self._normalized_comparisons(
            transformed, order, row_count
        )
        time_changes = self._time_changes(transformed, order, row_count)
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
            "summaryFacts": {
                "schemaVersion": "2.0",
                "reportBreakdown": self._report_breakdown(order, chart_rows),
                "reportMeasures": self._report_measure_results(
                    order, row_count, preview_rows
                ),
                "reportComparisons": summary_comparisons,
                "normalizedComparisons": normalized_comparisons,
                "timeChanges": time_changes,
            },
            "warnings": [],
            "artifact": {"artifactId": str(artifact_id), "format": "PARQUET",
                         "bucket": "results", "objectKey": object_key, "sizeBytes": size},
        }

    @staticmethod
    def _report_breakdown(
        order: ReportOrder, rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Return aggregate result rows safe for management-summary generation."""
        allowed_fields = {
            *(
                field for field in order.payload.group_by
                if not _SENSITIVE_SUMMARY_FIELD.search(field)
            ),
            *(
                item.alias for item in order.payload.temporal_group_by
                if not _SENSITIVE_SUMMARY_FIELD.search(item.alias)
            ),
            *(item.alias for item in order.payload.aggregations),
        }
        breakdown: list[dict[str, Any]] = []
        for row in rows:
            item = {
                field: SparkReportExecutor._summary_value(value)
                for field, value in row.items()
                if field in allowed_fields
                and isinstance(value, (str, int, float, bool, Decimal, date, datetime))
                or field in allowed_fields and value is None
            }
            if item and item not in breakdown:
                breakdown.append(item)
        additive_aliases = {
            item.alias for item in order.payload.aggregations
            if item.function in {AggregationFunction.SUM, AggregationFunction.COUNT}
        }
        totals = {
            alias: sum(
                float(row[alias]) for row in breakdown
                if isinstance(row.get(alias), (int, float, Decimal))
            )
            for alias in additive_aliases
        }
        for row in breakdown:
            for alias, total in totals.items():
                value = row.get(alias)
                if total > 0 and isinstance(value, (int, float, Decimal)):
                    row[f"{alias}ShareOfTotalPercent"] = float(value) / total * 100
        return breakdown

    @staticmethod
    def _summary_value(value: Any) -> Any:
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return str(value)
        return value

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
    def _summary_comparisons(
        frame: DataFrame, order: ReportOrder, row_count: int,
    ) -> list[dict[str, Any]]:
        """Calculate typed extrema across the complete grouped result."""
        if row_count < 2 or not order.payload.aggregations:
            return []
        temporal_aliases = {item.alias for item in order.payload.temporal_group_by}
        dimensions = [
            item.alias or item.column
            for item in order.payload.select
            if item.column in order.payload.group_by
            or (item.alias or item.column) in temporal_aliases
        ]
        if not dimensions:
            return []
        numeric_fields = {
            field.name for field in frame.schema.fields
            if isinstance(field.dataType, NumericType)
        }
        measures = [
            item for item in order.payload.aggregations
            if item.alias in numeric_fields
        ][:5]
        if not measures:
            return []
        dimension_struct = spark_fn.struct(
            *(spark_fn.col(name).alias(name) for name in dimensions)
        )
        expressions = []
        for aggregation in measures:
            measure = aggregation.alias
            column = spark_fn.col(measure)
            expressions.extend([
                spark_fn.max(column).alias(f"{measure}__max"),
                spark_fn.min(column).alias(f"{measure}__min"),
                spark_fn.sum(column).alias(f"{measure}__sum"),
                spark_fn.max_by(dimension_struct, column).alias(f"{measure}__max_dimensions"),
                spark_fn.min_by(dimension_struct, column).alias(f"{measure}__min_dimensions"),
            ])
        aggregate = frame.agg(*expressions).first().asDict(recursive=True)
        tie_expressions = []
        for aggregation in measures:
            measure = aggregation.alias
            highest = aggregate.get(f"{measure}__max")
            lowest = aggregate.get(f"{measure}__min")
            if not isinstance(highest, (int, float, Decimal)) or not isinstance(
                lowest, (int, float, Decimal)
            ):
                continue
            tie_expressions.extend([
                spark_fn.sum(spark_fn.when(
                    spark_fn.col(measure).eqNullSafe(spark_fn.lit(highest)), 1,
                ).otherwise(0)).alias(f"{measure}__max_ties"),
                spark_fn.sum(spark_fn.when(
                    spark_fn.col(measure).eqNullSafe(spark_fn.lit(lowest)), 1,
                ).otherwise(0)).alias(f"{measure}__min_ties"),
            ])
        tie_counts = (
            frame.agg(*tie_expressions).first().asDict(recursive=True)
            if tie_expressions else {}
        )
        comparisons = []
        for aggregation in measures:
            measure = aggregation.alias
            highest = aggregate.get(f"{measure}__max")
            lowest = aggregate.get(f"{measure}__min")
            total = aggregate.get(f"{measure}__sum")
            if not isinstance(highest, (int, float, Decimal)) or not isinstance(
                lowest, (int, float, Decimal)
            ):
                continue
            highest_number = float(highest)
            lowest_number = float(lowest)
            difference = highest_number - lowest_number
            denominator = (abs(highest_number) + abs(lowest_number)) / 2
            percentage = (
                difference / denominator * 100
                if denominator != 0 else None
            )
            share = (
                highest_number / float(total) * 100
                if aggregation.function in {
                    AggregationFunction.SUM, AggregationFunction.COUNT,
                }
                and isinstance(total, (int, float, Decimal))
                and float(total) > 0 and lowest_number >= 0 else None
            )
            def safe_dimensions(value: object) -> dict[str, Any]:
                if not isinstance(value, dict):
                    return {}
                return {
                    key: (
                        item.isoformat() if isinstance(item, (date, datetime))
                        else str(item) if isinstance(item, Decimal)
                        else item
                    )
                    for key, item in value.items()
                    if isinstance(item, (str, int, float, bool, Decimal, date, datetime))
                    or item is None
                }

            comparisons.append({
                "measure": measure,
                "highest": {
                    "dimensions": safe_dimensions(aggregate.get(
                        f"{measure}__max_dimensions")),
                    "value": highest_number,
                },
                "lowest": {
                    "dimensions": safe_dimensions(aggregate.get(
                        f"{measure}__min_dimensions")),
                    "value": lowest_number,
                },
                "absoluteSpread": difference,
                "relativeSpread": (
                    {
                        "method": "SYMMETRIC_PERCENT_DIFFERENCE",
                        "percent": min(200.0, max(0.0, percentage)),
                        "meaning": "RELATIVE_SPREAD_BETWEEN_HIGHEST_AND_LOWEST",
                    }
                    if percentage is not None else None
                ),
                "highestShareOfTotalPercent": min(100.0, max(0.0, share))
                if share is not None else None,
                "highestTieCount": int(tie_counts.get(f"{measure}__max_ties", 1)),
                "lowestTieCount": int(tie_counts.get(f"{measure}__min_ties", 1)),
                "groupCount": row_count,
            })
        return comparisons

    @staticmethod
    def _report_measure_results(
        order: ReportOrder, row_count: int, preview_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Expose only complete-result scalar aggregates, never row-level preview values."""
        if row_count != 1 or not preview_rows or not order.payload.aggregations:
            return []
        row = preview_rows[0]
        return [
            {"measure": item.alias, "value": row[item.alias]}
            for item in order.payload.aggregations
            if isinstance(row.get(item.alias), (int, float, Decimal))
        ]

    @staticmethod
    def _time_changes(
        frame: DataFrame, order: ReportOrder, row_count: int,
    ) -> list[dict[str, Any]]:
        """Compare first and last complete periods only for safely additive measures."""
        if row_count < 2 or len(order.payload.temporal_group_by) != 1:
            return []
        temporal = order.payload.temporal_group_by[0]
        additive = [
            item for item in order.payload.aggregations
            if item.function in {AggregationFunction.SUM, AggregationFunction.COUNT}
        ][:5]
        if not additive:
            return []
        period_frame = frame.groupBy(temporal.alias).agg(*[
            spark_fn.sum(item.alias).alias(item.alias) for item in additive
        ]).orderBy(spark_fn.col(temporal.alias).asc())
        endpoints = period_frame.collect()
        if len(endpoints) < 2:
            return []
        earlier = endpoints[0].asDict(recursive=True)
        later = endpoints[-1].asDict(recursive=True)

        def display(value: Any) -> Any:
            if isinstance(value, (date, datetime)):
                return value.isoformat()
            if isinstance(value, Decimal):
                return str(value)
            return value

        facts = []
        for measure in additive:
            earlier_value = earlier.get(measure.alias)
            later_value = later.get(measure.alias)
            if not isinstance(earlier_value, (int, float, Decimal)) or not isinstance(
                later_value, (int, float, Decimal)
            ):
                continue
            earlier_number = float(earlier_value)
            later_number = float(later_value)
            absolute_change = later_number - earlier_number
            percentage_change = (
                absolute_change / abs(earlier_number) * 100
                if not math.isclose(earlier_number, 0.0, abs_tol=1e-12)
                else None
            )
            facts.append({
                "measure": measure.alias,
                "earlier": {
                    "dimensions": {temporal.alias: display(earlier.get(temporal.alias))},
                    "value": earlier_number,
                },
                "later": {
                    "dimensions": {temporal.alias: display(later.get(temporal.alias))},
                    "value": later_number,
                },
                "absoluteChange": absolute_change,
                "percentageChange": percentage_change,
            })
        return facts

    @staticmethod
    def _normalized_comparisons(
        frame: DataFrame, order: ReportOrder, row_count: int,
    ) -> list[dict[str, Any]]:
        """Compare SUM measures per counted item without inferring business direction."""
        if row_count < 2:
            return []
        count_measures = [
            item for item in order.payload.aggregations
            if item.function in {
                AggregationFunction.COUNT, AggregationFunction.COUNT_DISTINCT,
            }
        ]
        numerators = [
            item for item in order.payload.aggregations
            if item.function == AggregationFunction.SUM
        ]
        if not count_measures or not numerators:
            return []
        temporal_aliases = {item.alias for item in order.payload.temporal_group_by}
        dimensions = [
            item.alias or item.column
            for item in order.payload.select
            if item.column in order.payload.group_by
            or (item.alias or item.column) in temporal_aliases
        ]
        if not dimensions:
            return []
        dimension_struct = spark_fn.struct(
            *(spark_fn.col(name).alias(name) for name in dimensions)
        )
        approved = []
        for denominator in count_measures[:1]:
            for numerator in numerators[:5]:
                ratio_name = f"__{numerator.alias}_per_{denominator.alias}"
                ratio = spark_fn.when(
                    spark_fn.col(denominator.alias) != 0,
                    spark_fn.col(numerator.alias).cast("double")
                    / spark_fn.col(denominator.alias).cast("double"),
                )
                ratio_frame = frame.withColumn(ratio_name, ratio).filter(
                    spark_fn.col(ratio_name).isNotNull()
                )
                aggregate = ratio_frame.agg(
                    spark_fn.max(ratio_name).alias("maximum"),
                    spark_fn.min(ratio_name).alias("minimum"),
                    spark_fn.max_by(dimension_struct, spark_fn.col(ratio_name)).alias(
                        "maximum_dimensions"
                    ),
                    spark_fn.min_by(dimension_struct, spark_fn.col(ratio_name)).alias(
                        "minimum_dimensions"
                    ),
                ).first().asDict(recursive=True)
                maximum = aggregate.get("maximum")
                minimum = aggregate.get("minimum")
                if not isinstance(maximum, (int, float, Decimal)) or not isinstance(
                    minimum, (int, float, Decimal)
                ):
                    continue
                maximum_number = float(maximum)
                minimum_number = float(minimum)
                difference = maximum_number - minimum_number
                midpoint = (abs(maximum_number) + abs(minimum_number)) / 2
                percent = difference / midpoint * 100 if midpoint else None

                def safe(value: object) -> dict[str, Any]:
                    if not isinstance(value, dict):
                        return {}
                    return {
                        key: (
                            item.isoformat() if isinstance(item, (date, datetime))
                            else str(item) if isinstance(item, Decimal)
                            else item
                        )
                        for key, item in value.items()
                        if isinstance(
                            item, (str, int, float, bool, Decimal, date, datetime)
                        ) or item is None
                    }

                approved.append({
                    "numeratorMeasure": numerator.alias,
                    "denominatorMeasure": denominator.alias,
                    "highest": {
                        "dimensions": safe(aggregate.get("maximum_dimensions")),
                        "value": maximum_number,
                    },
                    "lowest": {
                        "dimensions": safe(aggregate.get("minimum_dimensions")),
                        "value": minimum_number,
                    },
                    "absoluteSpread": difference,
                    "relativeSpread": (
                        {
                            "method": "SYMMETRIC_PERCENT_DIFFERENCE",
                            "percent": min(200.0, max(0.0, percent)),
                            "meaning": "RELATIVE_SPREAD_BETWEEN_HIGHEST_AND_LOWEST",
                        }
                        if percent is not None else None
                    ),
                })
        return approved

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
        display_labels = SparkReportExecutor._display_labels(order)
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
                "title": display_labels.get(value, SparkReportExecutor._fallback_label(value)),
                "valueField": value,
                "valueLabel": display_labels.get(
                    value, SparkReportExecutor._fallback_label(value)
                ),
                "categoryField": category,
                "categoryLabel": display_labels.get(
                    category, SparkReportExecutor._fallback_label(category)
                ),
                "seriesField": series_field,
                "seriesLabel": (
                    display_labels.get(
                        series_field, SparkReportExecutor._fallback_label(series_field)
                    )
                    if series_field else None
                ),
                "categories": categories,
                "series": series,
            })
        return charts

    @staticmethod
    def _fallback_label(field: str) -> str:
        return field.replace("_", " ").strip().title()
