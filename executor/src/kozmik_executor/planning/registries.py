from .models import AggregationFunction, DataType, FilterOperator, TemporalGranularity

APPROVED_FILTER_OPERATORS = frozenset(FilterOperator)
APPROVED_AGGREGATIONS = frozenset(AggregationFunction)
APPROVED_TEMPORAL_GRANULARITIES = frozenset(TemporalGranularity)
NUMERIC_TYPES = frozenset({DataType.INTEGER, DataType.LONG, DataType.DECIMAL})
ORDERED_TYPES = frozenset({
    DataType.STRING, DataType.INTEGER, DataType.LONG, DataType.DECIMAL,
    DataType.DATE, DataType.TIMESTAMP,
})
FILTER_TYPES = {
    FilterOperator.CONTAINS: frozenset({DataType.STRING}),
    FilterOperator.STARTS_WITH: frozenset({DataType.STRING}),
    FilterOperator.ENDS_WITH: frozenset({DataType.STRING}),
    FilterOperator.GT: ORDERED_TYPES,
    FilterOperator.GTE: ORDERED_TYPES,
    FilterOperator.LT: ORDERED_TYPES,
    FilterOperator.LTE: ORDERED_TYPES,
    FilterOperator.BETWEEN: ORDERED_TYPES,
}
