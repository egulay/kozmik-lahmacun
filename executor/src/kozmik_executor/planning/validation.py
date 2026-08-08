from dataclasses import dataclass
import re

from .models import (
    AggregationFunction,
    AuthorizedColumn,
    DataType,
    DerivedFieldOperation,
    FilterExpression,
    FilterItem,
    FilterOperator,
    ReportOrder,
    ReportPlanningRequest,
    ValidationIssue,
)
from .registries import FILTER_TYPES, NUMERIC_TYPES


@dataclass
class PlanningValidationError(Exception):
    issues: list[ValidationIssue]


def validate_order(order: ReportOrder, request: ReportPlanningRequest) -> None:
    issues: list[ValidationIssue] = []
    if order.entity_id != request.authorized_schema.entity_id:
        issues.append(ValidationIssue(code="ENTITY_MISMATCH", path="entityId",
                                      message="Order entity is not authorized"))
    if not set(request.capabilities).intersection({"REPORTER", "SCIENTIST", "ADMIN"}):
        issues.append(ValidationIssue(code="ROLE_NOT_AUTHORIZED", path="capabilities",
                                      message="A reporting-capable role is required"))
    columns = {item.column_name: item for item in request.authorized_schema.columns}

    arithmetic = {
        DerivedFieldOperation.ADD, DerivedFieldOperation.SUBTRACT,
        DerivedFieldOperation.MULTIPLY, DerivedFieldOperation.DIVIDE,
    }
    string_operations = {
        DerivedFieldOperation.LOWER, DerivedFieldOperation.UPPER,
        DerivedFieldOperation.TRIM, DerivedFieldOperation.LENGTH,
        DerivedFieldOperation.SUBSTRING, DerivedFieldOperation.REPLACE,
    }
    date_operations = {
        DerivedFieldOperation.YEAR, DerivedFieldOperation.QUARTER,
        DerivedFieldOperation.MONTH, DerivedFieldOperation.DAY,
        DerivedFieldOperation.DAY_OF_WEEK, DerivedFieldOperation.DATE_ADD_DAYS,
        DerivedFieldOperation.DATE_DIFF_DAYS,
    }
    for index, item in enumerate(order.payload.derived_fields):
        path = f"payload.derivedFields[{index}]"
        source = columns.get(item.column)
        if source is None:
            issues.append(ValidationIssue(
                code="COLUMN_NOT_AUTHORIZED", path=f"{path}.column",
                message=f"Column '{item.column}' is not in the schema",
            ))
            continue
        if item.alias in columns:
            issues.append(ValidationIssue(
                code="OUTPUT_ALIAS_DUPLICATED", path=f"{path}.alias",
                message=f"Output alias '{item.alias}' is already in use",
            ))
            continue
        output_type = source.data_type
        operand = columns.get(item.operand_column) if item.operand_column else None
        if item.operand_column and operand is None:
            issues.append(ValidationIssue(
                code="COLUMN_NOT_AUTHORIZED", path=f"{path}.operandColumn",
                message=f"Column '{item.operand_column}' is not in the schema",
            ))
        if item.operation in arithmetic:
            output_type = DataType.DECIMAL
            if source.data_type not in NUMERIC_TYPES or (
                operand and operand.data_type not in NUMERIC_TYPES
            ):
                issues.append(ValidationIssue(
                    code="DERIVED_FIELD_TYPE_MISMATCH", path=path,
                    message="Arithmetic operations require numeric columns",
                ))
            if (item.operand_column is None) == (item.operand_value is None):
                issues.append(ValidationIssue(
                    code="DERIVED_FIELD_OPERAND_INVALID", path=path,
                    message="Arithmetic operations require exactly one column or literal operand",
                ))
            if item.operand_value is not None and not isinstance(
                item.operand_value, (int, float)
            ):
                issues.append(ValidationIssue(
                    code="DERIVED_FIELD_OPERAND_INVALID", path=f"{path}.operandValue",
                    message="Arithmetic literal operands must be numeric",
                ))
        elif item.operation in string_operations:
            if source.data_type != DataType.STRING:
                issues.append(ValidationIssue(
                    code="DERIVED_FIELD_TYPE_MISMATCH", path=path,
                    message="String transformations require a STRING column",
                ))
            output_type = (
                DataType.INTEGER if item.operation == DerivedFieldOperation.LENGTH
                else DataType.STRING
            )
            if item.operation == DerivedFieldOperation.SUBSTRING and (
                item.start is None or item.length is None
            ):
                issues.append(ValidationIssue(
                    code="DERIVED_FIELD_ARGUMENT_REQUIRED", path=path,
                    message="SUBSTRING requires start and length",
                ))
            if item.operation == DerivedFieldOperation.REPLACE and item.search is None:
                issues.append(ValidationIssue(
                    code="DERIVED_FIELD_ARGUMENT_REQUIRED", path=path,
                    message="REPLACE requires search text",
                ))
        elif item.operation in date_operations:
            if source.data_type not in {DataType.DATE, DataType.TIMESTAMP}:
                issues.append(ValidationIssue(
                    code="DERIVED_FIELD_TYPE_MISMATCH", path=path,
                    message="Date transformations require a DATE or TIMESTAMP column",
                ))
            output_type = (
                source.data_type if item.operation == DerivedFieldOperation.DATE_ADD_DAYS
                else DataType.INTEGER
            )
            if item.operation == DerivedFieldOperation.DATE_ADD_DAYS and not isinstance(
                item.operand_value, int
            ):
                issues.append(ValidationIssue(
                    code="DERIVED_FIELD_ARGUMENT_REQUIRED", path=path,
                    message="DATE_ADD_DAYS requires an integer operandValue",
                ))
            if item.operation == DerivedFieldOperation.DATE_DIFF_DAYS and (
                operand is None or operand.data_type not in {DataType.DATE, DataType.TIMESTAMP}
            ):
                issues.append(ValidationIssue(
                    code="DERIVED_FIELD_ARGUMENT_REQUIRED", path=path,
                    message="DATE_DIFF_DAYS requires a DATE or TIMESTAMP operandColumn",
                ))
        elif item.operation == DerivedFieldOperation.COALESCE:
            if item.operand_value is None:
                issues.append(ValidationIssue(
                    code="DERIVED_FIELD_ARGUMENT_REQUIRED", path=path,
                    message="COALESCE requires a non-null replacement operandValue",
                ))
        columns[item.alias] = AuthorizedColumn(
            columnName=item.alias,
            businessName=item.display_label or item.alias,
            dataType=output_type,
        )

    def column(name: str | None, path: str, direct_access: bool = True):
        if name is None:
            return None
        item = columns.get(name)
        if item is None:
            issues.append(ValidationIssue(code="COLUMN_NOT_AUTHORIZED", path=path,
                                          message=f"Column '{name}' is not in the schema"))
        return item

    for index, item in enumerate(order.payload.select):
        column(item.column, f"payload.select[{index}].column")
    for index, name in enumerate(order.payload.group_by):
        column(name, f"payload.groupBy[{index}]")
    temporal_groups = {
        item.alias: item for item in order.payload.temporal_group_by
    }
    if len(temporal_groups) != len(order.payload.temporal_group_by):
        issues.append(ValidationIssue(
            code="TEMPORAL_ALIAS_DUPLICATED",
            path="payload.temporalGroupBy",
            message="Temporal grouping aliases must be unique",
        ))
    for index, item in enumerate(order.payload.temporal_group_by):
        metadata = column(item.column, f"payload.temporalGroupBy[{index}].column")
        if metadata and metadata.data_type not in {DataType.DATE, DataType.TIMESTAMP}:
            issues.append(ValidationIssue(
                code="TEMPORAL_GROUP_TYPE_MISMATCH",
                path=f"payload.temporalGroupBy[{index}].column",
                message="Temporal grouping requires a DATE or TIMESTAMP column",
            ))
    numeric_range_groups = {
        item.alias: item for item in order.payload.numeric_range_group_by
    }
    range_wording = re.search(
        r"\b(?:range|ranges|band|bands|bracket|brackets|bucket|buckets|"
        r"aralık\w*|aralığ\w*|dilim\w*|bant\w*)\b",
        request.user_request.casefold(),
    )
    grouping_wording = re.search(
        r"\b(?:group|grouped|grouping|distribution|breakdown|"
        r"grupla|gruplandır|gruplama|dağılım)\w*\b",
        request.user_request.casefold(),
    )
    exactly_grouped_numeric = any(
        columns.get(name) and columns[name].data_type in NUMERIC_TYPES
        for name in order.payload.group_by
    )
    if (
        range_wording and grouping_wording and exactly_grouped_numeric
        and not numeric_range_groups
    ):
        issues.append(ValidationIssue(
            code="NUMERIC_RANGE_GROUP_REQUIRED",
            path="payload.numericRangeGroupBy",
            message=(
                "The request asks for numeric ranges; define governed numeric buckets "
                "instead of grouping by each exact numeric value"
            ),
        ))
    if len(numeric_range_groups) != len(order.payload.numeric_range_group_by):
        issues.append(ValidationIssue(
            code="NUMERIC_RANGE_ALIAS_DUPLICATED",
            path="payload.numericRangeGroupBy",
            message="Numeric range grouping aliases must be unique",
        ))
    for index, item in enumerate(order.payload.numeric_range_group_by):
        path = f"payload.numericRangeGroupBy[{index}]"
        metadata = column(item.column, f"{path}.column")
        if metadata and metadata.data_type not in NUMERIC_TYPES:
            issues.append(ValidationIssue(
                code="NUMERIC_RANGE_TYPE_MISMATCH", path=f"{path}.column",
                message="Numeric range grouping requires a numeric column",
            ))
        if item.alias in temporal_groups:
            issues.append(ValidationIssue(
                code="OUTPUT_ALIAS_DUPLICATED", path=f"{path}.alias",
                message=f"Output alias '{item.alias}' is already in use",
            ))
        buckets = item.buckets
        if buckets[0].lower_bound is not None or buckets[-1].upper_bound is not None:
            issues.append(ValidationIssue(
                code="NUMERIC_RANGES_NOT_EXHAUSTIVE", path=f"{path}.buckets",
                message="Numeric ranges must cover values below the first and above the last boundary",
            ))
        for bucket_index, (previous, current) in enumerate(zip(buckets, buckets[1:]), 1):
            if previous.upper_bound != current.lower_bound:
                issues.append(ValidationIssue(
                    code="NUMERIC_RANGES_NOT_CONTIGUOUS",
                    path=f"{path}.buckets[{bucket_index}]",
                    message="Numeric ranges must be ordered and contiguous",
                ))
            elif previous.include_upper == current.include_lower:
                issues.append(ValidationIssue(
                    code="NUMERIC_RANGE_BOUNDARY_INVALID",
                    path=f"{path}.buckets[{bucket_index}]",
                    message="Each shared boundary must belong to exactly one range",
                ))
    output_names = {
        item.alias or item.column for item in order.payload.select
    } | {
        item.alias for item in order.payload.aggregations
    } | {
        item.alias for item in order.payload.calculated_metrics
    } | set(temporal_groups) | set(numeric_range_groups)
    if order.payload.aggregations:
        aggregation_source_columns = {
            item.column for item in order.payload.aggregations if item.column is not None
        }
        for index, item in enumerate(order.payload.select):
            temporal_match = any(
                group.column == item.column
                and group.alias == (item.alias or item.column)
                for group in order.payload.temporal_group_by
            )
            numeric_range_match = any(
                group.column == item.column
                and group.alias == (item.alias or item.column)
                for group in order.payload.numeric_range_group_by
            )
            if (
                item.column not in order.payload.group_by
                and item.column not in aggregation_source_columns
                and not temporal_match
                and not numeric_range_match
            ):
                issues.append(ValidationIssue(
                    code="SELECT_FIELD_NOT_GROUPED",
                    path=f"payload.select[{index}].column",
                    message=f"Selected field '{item.column}' must be present in groupBy",
                ))
    for index, item in enumerate(order.payload.order_by):
        if item.column not in output_names:
            issues.append(ValidationIssue(
                code="ORDER_FIELD_NOT_AVAILABLE",
                path=f"payload.orderBy[{index}].column",
                message=f"Order field '{item.column}' is not present in the report output",
            ))
    def validate_condition(
        item: FilterItem, path: str, available: dict[str, object] | None = None,
    ) -> None:
        metadata = available.get(item.column) if available is not None else column(
            item.column, f"{path}.column")
        if available is not None and metadata is None:
            issues.append(ValidationIssue(
                code="HAVING_FIELD_NOT_AVAILABLE", path=f"{path}.column",
                message=f"Having field '{item.column}' is not a grouped output or aggregation",
            ))
        allowed_types = FILTER_TYPES.get(item.operator)
        if metadata and allowed_types and metadata.data_type not in allowed_types:
            issues.append(ValidationIssue(code="OPERATOR_TYPE_MISMATCH",
                                          path=f"{path}.operator",
                                          message="Operator is not approved for the column type"))
        vocabulary = getattr(metadata, "categorical_values", []) if metadata else []
        if vocabulary and item.operator in {
            FilterOperator.EQ, FilterOperator.NE, FilterOperator.IN, FilterOperator.NOT_IN,
        }:
            supplied = item.values if item.operator in {
                FilterOperator.IN, FilterOperator.NOT_IN,
            } else [item.value]
            invalid = [value for value in (supplied or []) if value not in vocabulary]
            if invalid:
                issues.append(ValidationIssue(
                    code="CATEGORICAL_VALUE_NOT_APPROVED",
                    path=f"{path}.value",
                    message=(
                        f"Use an exact approved value for '{item.column}'. "
                        f"Approved values: {', '.join(vocabulary)}"
                    ),
                ))
        if item.operator in {FilterOperator.IN, FilterOperator.NOT_IN, FilterOperator.BETWEEN}:
            expected = 2 if item.operator == FilterOperator.BETWEEN else 1
            if item.values is None or len(item.values) < expected:
                issues.append(ValidationIssue(code="FILTER_VALUES_REQUIRED",
                                              path=f"{path}.values",
                                              message="Operator requires bounded values"))
        elif item.operator in {FilterOperator.IS_NULL, FilterOperator.IS_NOT_NULL}:
            if item.value is not None or item.values is not None:
                issues.append(ValidationIssue(code="FILTER_VALUE_FORBIDDEN",
                                              path=path,
                                              message="Null operator accepts no value"))
        elif item.value is None:
            issues.append(ValidationIssue(code="FILTER_VALUE_REQUIRED",
                                          path=f"{path}.value",
                                          message="Operator requires a value"))

    def validate_expression(
        expression: FilterExpression, path: str, available: dict[str, object] | None = None,
        depth: int = 1, state: list[int] | None = None,
    ) -> None:
        counters = state if state is not None else [0]
        counters[0] += 1
        if counters[0] > 100:
            issues.append(ValidationIssue(
                code="FILTER_EXPRESSION_TOO_LARGE", path=path,
                message="Boolean expression may contain at most 100 nodes",
            ))
            return
        if depth > 5:
            issues.append(ValidationIssue(
                code="FILTER_EXPRESSION_TOO_DEEP", path=path,
                message="Boolean expression nesting may not exceed 5 levels",
            ))
            return
        if isinstance(expression, FilterItem):
            validate_condition(expression, path, available)
            return
        for child_index, child in enumerate(expression.children):
            validate_expression(
                child, f"{path}.children[{child_index}]", available, depth + 1, counters)

    if isinstance(order.payload.filters, list):
        for index, item in enumerate(order.payload.filters):
            validate_condition(item, f"payload.filters[{index}]")
    else:
        validate_expression(order.payload.filters, "payload.filters")
    for index, item in enumerate(order.payload.aggregations):
        metadata = column(
            item.column, f"payload.aggregations[{index}].column", direct_access=False)
        if metadata and item.function in {
            AggregationFunction.SUM, AggregationFunction.AVG,
            AggregationFunction.MEDIAN, AggregationFunction.PERCENTILE,
            AggregationFunction.VARIANCE, AggregationFunction.STDDEV,
        }:
            if metadata.data_type not in NUMERIC_TYPES:
                issues.append(ValidationIssue(code="AGGREGATION_TYPE_MISMATCH",
                                              path=f"payload.aggregations[{index}].function",
                                              message="Aggregation requires a numeric column"))
        if metadata and item.function in {AggregationFunction.MIN, AggregationFunction.MAX}:
            if metadata.data_type == DataType.BOOLEAN:
                issues.append(ValidationIssue(
                    code="AGGREGATION_TYPE_MISMATCH",
                    path=f"payload.aggregations[{index}].function",
                    message="MIN and MAX are not approved for BOOLEAN columns",
                ))
        if item.filter is not None:
            validate_expression(item.filter, f"payload.aggregations[{index}].filter")
    aggregation_aliases = {item.alias for item in order.payload.aggregations}
    pre_calculated_outputs = {
        item.alias or item.column for item in order.payload.select
    } | aggregation_aliases | set(temporal_groups) | set(numeric_range_groups)
    calculated_aliases: set[str] = set()
    for index, item in enumerate(order.payload.calculated_metrics):
        for field, value in (
            ("numerator", item.numerator), ("denominator", item.denominator),
        ):
            if value not in aggregation_aliases and value not in calculated_aliases:
                issues.append(ValidationIssue(
                    code="CALCULATED_METRIC_SOURCE_NOT_AVAILABLE",
                    path=f"payload.calculatedMetrics[{index}].{field}",
                    message=(
                        f"Calculated metric source '{value}' must reference an earlier "
                        "aggregation or calculated metric"
                    ),
                ))
        if item.alias in pre_calculated_outputs or item.alias in calculated_aliases:
            issues.append(ValidationIssue(
                code="OUTPUT_ALIAS_DUPLICATED",
                path=f"payload.calculatedMetrics[{index}].alias",
                message=f"Output alias '{item.alias}' is already in use",
            ))
        calculated_aliases.add(item.alias)
    if order.payload.having is not None:
        having_columns: dict[str, object] = {}
        for item in order.payload.select:
            if item.column in order.payload.group_by:
                metadata = columns.get(item.column)
                if metadata:
                    having_columns[item.alias or item.column] = metadata
            if (
                item.alias in numeric_range_groups
                and numeric_range_groups[item.alias].column == item.column
            ):
                having_columns[item.alias] = type(
                    "HavingMetadata", (), {"data_type": DataType.STRING})()
        for item in order.payload.aggregations:
            source = columns.get(item.column) if item.column else None
            data_type = (
                DataType.LONG
                if item.function in {AggregationFunction.COUNT,
                                     AggregationFunction.COUNT_DISTINCT}
                else DataType.DECIMAL
                if item.function in {AggregationFunction.SUM, AggregationFunction.AVG}
                else source.data_type if source else DataType.LONG
            )
            having_columns[item.alias] = type(
                "HavingMetadata", (), {"data_type": data_type})()
        for item in order.payload.calculated_metrics:
            having_columns[item.alias] = type(
                "HavingMetadata", (), {"data_type": DataType.DECIMAL})()
        validate_expression(order.payload.having, "payload.having", having_columns)
    for index, hint in enumerate(order.payload.chart_hints):
        for value, suffix in (
            (hint.category_column, "categoryColumn"),
            (hint.value_column, "valueColumn"),
        ):
            if value is not None and value not in output_names:
                issues.append(ValidationIssue(
                    code="CHART_FIELD_NOT_AVAILABLE",
                    path=f"payload.chartHints[{index}].{suffix}",
                    message=f"Chart field '{value}' is not present in the report output",
                ))
    if issues:
        raise PlanningValidationError(issues)
