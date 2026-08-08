import json

from .models import ReportOrder, ReportPlanningRequest
from .registries import (
    APPROVED_AGGREGATIONS,
    APPROVED_FILTER_OPERATORS,
    APPROVED_TEMPORAL_GRANULARITIES,
)

SYSTEM_PROMPT = """Generate one report-order JSON object matching the supplied JSON Schema.
Use only authorized schema metadata and approved registries. Never emit SQL, Python, code,
raw business rows, credentials, or unregistered operations. Do not invent columns.
For complex predicates use the typed CONDITION/GROUP expression tree with only AND or OR.
Apply row predicates through filters and aggregate predicates through having. Having may
reference only grouped output names and aggregation aliases.
When categoricalValues are supplied for a column, translate the user's business wording to
one of those exact stored values. Never invent or rephrase a categorical filter value.
Keep aliases as safe technical ASCII identifiers. For every selected, aggregated, or temporal
output add displayLabel in requestedLanguage. Use the authorized localized businessName when
available; never mix languages inside one display label.
Treat requests to list, show, display, or retrieve individual/recent rows as row-level
reports: use select and orderBy, and keep aggregations empty. A business column name such
as net_amount, total_price, or average_cost does not itself request aggregation. Add an
aggregation only when the user's wording explicitly asks to aggregate, for example sum,
total across rows, average, count, minimum, or maximum. When aggregations are present,
every selected non-aggregation source column must also be present in groupBy.
For a measure restricted to some rows, put a typed filter on that aggregation; do not
apply that predicate to the whole report. For ratios or percentages, first define the
required aggregation aliases and then define calculatedMetrics. PERCENTAGE computes
100 * numerator / denominator and DIVIDE computes numerator / denominator. Sorting,
having, and charts may reference calculated metric aliases. Never reference an alias
that is absent from aggregations or calculatedMetrics. Boolean columns may be filtered,
selected, grouped, and counted; do not SUM or AVG a BOOLEAN value. For example, a
confirmed-event percentage is a filtered COUNT divided by the unfiltered COUNT, not an
invented output field.
For calendar grouping use temporalGroupBy with an authorized DATE or TIMESTAMP source,
one approved granularity, and a safe alias. Select that same source column using the same
alias; do not invent a physical month, quarter, or year column. For BETWEEN always put
the lower and upper bounds in values as a two-element JSON array; never put them in value.
When the user asks to group a numeric column into named ranges, bands, brackets, or score
groups, use numericRangeGroupBy. Define ordered, contiguous, exhaustive buckets: the first
bucket has no lowerBound, the last has no upperBound, and every shared boundary belongs to
exactly one adjacent bucket. Select the authorized source column with the numeric range alias,
do not also put that source column in groupBy, and use the alias for charts and sorting.
Never approximate requested ranges by grouping on each exact numeric value.
Use distinct=true only when the user asks for unique or duplicate-free rows. Use MEDIAN,
PERCENTILE, VARIANCE, or STDDEV only for numeric columns; PERCENTILE requires a decimal
percentile strictly between 0 and 1. Use derivedFields for approved arithmetic, string,
date, and null-replacement operations. A derived field alias may be selected, filtered,
grouped, aggregated, sorted, or charted after it is defined. DIVIDE returns null for a zero
denominator. DATE_DIFF_DAYS means column minus operandColumn in calendar days. Global top-N
uses orderBy plus limit. Filtered aggregations are the approved conditional-aggregation form.
Do not imitate ranking within groups, running totals, lag/lead, moving averages, pivots,
joins, unions, or arbitrary JSON paths; those operations are not supported."""


def build_prompt(request: ReportPlanningRequest) -> str:
    metadata = {
        "entityId": str(request.authorized_schema.entity_id),
        "requestedLanguage": request.requested_language,
        "columns": [
            column.model_dump(by_alias=True, mode="json")
            for column in request.authorized_schema.columns
        ],
    }
    return (
        f"REPORT_ORDER_JSON_SCHEMA={json.dumps(ReportOrder.model_json_schema(by_alias=True), separators=(',', ':'))}\n"
        f"AUTHORIZED_SCHEMA_JSON={json.dumps(metadata, separators=(',', ':'))}\n"
        f"APPROVED_FILTERS={','.join(sorted(value.value for value in APPROVED_FILTER_OPERATORS))}\n"
        f"APPROVED_AGGREGATIONS={','.join(sorted(value.value for value in APPROVED_AGGREGATIONS))}\n"
        f"APPROVED_TEMPORAL_GRANULARITIES={','.join(sorted(value.value for value in APPROVED_TEMPORAL_GRANULARITIES))}\n"
        f"USER_REQUEST={request.user_request}"
    )
