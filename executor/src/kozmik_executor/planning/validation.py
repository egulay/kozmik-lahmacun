from dataclasses import dataclass

from .models import (
    AggregationFunction,
    DataType,
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
    output_names = {
        item.alias or item.column for item in order.payload.select
    } | {
        item.alias for item in order.payload.aggregations
    } | set(temporal_groups)
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
            if (
                item.column not in order.payload.group_by
                and item.column not in aggregation_source_columns
                and not temporal_match
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
        if metadata and item.function in {AggregationFunction.SUM, AggregationFunction.AVG}:
            if metadata.data_type not in NUMERIC_TYPES:
                issues.append(ValidationIssue(code="AGGREGATION_TYPE_MISMATCH",
                                              path=f"payload.aggregations[{index}].function",
                                              message="Aggregation requires a numeric column"))
    if order.payload.having is not None:
        having_columns: dict[str, object] = {}
        for item in order.payload.select:
            if item.column in order.payload.group_by:
                metadata = columns.get(item.column)
                if metadata:
                    having_columns[item.alias or item.column] = metadata
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
