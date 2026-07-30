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
Keep aliases as safe technical ASCII identifiers. For every selected, aggregated, or temporal
output add displayLabel in requestedLanguage. Use the authorized localized businessName when
available; never mix languages inside one display label.
Treat requests to list, show, display, or retrieve individual/recent rows as row-level
reports: use select and orderBy, and keep aggregations empty. A business column name such
as net_amount, total_price, or average_cost does not itself request aggregation. Add an
aggregation only when the user's wording explicitly asks to aggregate, for example sum,
total across rows, average, count, minimum, or maximum. When aggregations are present,
every selected non-aggregation source column must also be present in groupBy.
For calendar grouping use temporalGroupBy with an authorized DATE or TIMESTAMP source,
one approved granularity, and a safe alias. Select that same source column using the same
alias; do not invent a physical month, quarter, or year column. For BETWEEN always put
the lower and upper bounds in values as a two-element JSON array; never put them in value."""


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
