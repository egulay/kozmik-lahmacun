import json
import logging
import os
import re
import secrets
import unicodedata

from fastapi import APIRouter, Header, HTTPException
from pydantic import ValidationError

from kozmik_executor.chat.api import configuration_client, provider_registry
from kozmik_executor.chat.providers import ProviderError

from .models import (
    MlOrder,
    MlPlanningResponse,
    ReportOrder,
    ReportPlanningRequest,
    ReportPlanningResponse,
    ValidationIssue,
)
from .ml import ALGORITHM_REGISTRY, ML_SYSTEM_PROMPT, validate_ml_order
from .prompts import SYSTEM_PROMPT, build_prompt
from .validation import PlanningValidationError, validate_order

router = APIRouter(prefix="/internal/v1/plans")
logger = logging.getLogger(__name__)


def _authenticate(value: str | None) -> None:
    expected = os.environ.get("INTERNAL_API_KEY", "")
    if not expected or value is None or not secrets.compare_digest(expected, value):
        raise HTTPException(status_code=401, detail="internal authentication required")


def _enforce_execution_constraints(
    raw: object, max_preview_rows: int, timeout_seconds: int,
) -> None:
    """Keep operational execution limits under control-plane ownership."""
    if not isinstance(raw, dict):
        return
    constraints = raw.get("constraints")
    if not isinstance(constraints, dict):
        return
    constraints["maxPreviewRows"] = max(1, min(max_preview_rows, 100))
    constraints["timeoutSeconds"] = max(1, min(timeout_seconds, 21_600))


def _report_issues(exception: ValidationError | PlanningValidationError) -> list[dict]:
    if isinstance(exception, ValidationError):
        return [
            {
                "code": "ORDER_SCHEMA_INVALID",
                "path": ".".join(map(str, error["loc"])),
                "message": error["msg"],
            }
            for error in exception.errors()
        ]
    return [issue.model_dump(by_alias=True) for issue in exception.issues]


async def _generate_report_order(
    provider, request: ReportPlanningRequest, max_preview_rows: int = 100,
    timeout_seconds: int = 7200,
) -> ReportOrder:
    base_prompt = build_prompt(request)
    prompt = base_prompt
    last_exception: ValidationError | PlanningValidationError | None = None
    for attempt in range(3):
        raw = await provider.complete_json(SYSTEM_PROMPT, prompt)
        try:
            _enforce_execution_constraints(raw, max_preview_rows, timeout_seconds)
            _normalize_order_identifiers(raw)
            _normalize_between_filters(raw)
            _normalize_explicit_temporal_grouping(raw)
            _normalize_implicit_temporal_grouping(raw, request)
            _normalize_temporal_labels(raw, request.requested_language)
            _normalize_group_by_aliases(raw)
            order = ReportOrder.model_validate(raw)
            validate_order(order, request)
            return order
        except (ValidationError, PlanningValidationError) as exception:
            last_exception = exception
            issues = _report_issues(exception)
            logger.warning(
                "report_order_validation_failed attempt=%s issues=%s",
                attempt + 1,
                [{"code": issue["code"], "path": issue["path"]} for issue in issues],
            )
            prompt = (
                f"{base_prompt}\n"
                f"REJECTED_ORDER={json.dumps(raw, separators=(',', ':'), default=str)}\n"
                f"VALIDATION_ERRORS={json.dumps(issues, separators=(',', ':'))}\n"
                "Regenerate the complete JSON object. Correct every validation error. "
                "Array fields must always be JSON arrays, including when empty."
            )
    if last_exception is None:
        raise RuntimeError("report generation ended without an order")
    raise last_exception


def _normalize_order_identifiers(raw: object) -> None:
    """Separate human labels from safe internal aliases without changing source columns."""
    if not isinstance(raw, dict) or not isinstance(raw.get("payload"), dict):
        return
    payload = raw["payload"]
    valid = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
    translation = str.maketrans({
        "ç": "c", "Ç": "C", "ğ": "g", "Ğ": "G", "ı": "i", "İ": "I",
        "ö": "o", "Ö": "O", "ş": "s", "Ş": "S", "ü": "u", "Ü": "U",
    })
    replacements: dict[str, str] = {}
    used: set[str] = set()

    def safe_identifier(value: str) -> str:
        translated = unicodedata.normalize("NFKD", value.translate(translation))
        ascii_value = "".join(
            character for character in translated if not unicodedata.combining(character)
        )
        normalized = re.sub(r"[^A-Za-z0-9_]+", "_", ascii_value).strip("_").lower()
        if not normalized:
            normalized = "field"
        if normalized[0].isdigit():
            normalized = f"field_{normalized}"
        return normalized[:100]

    collections = (
        payload.get("select"), payload.get("aggregations"),
        payload.get("temporalGroupBy"),
    )
    for collection in collections:
        if isinstance(collection, list):
            used.update(
                item["alias"] for item in collection
                if isinstance(item, dict)
                and isinstance(item.get("alias"), str)
                and valid.fullmatch(item["alias"])
            )
    changed = 0
    for collection in collections:
        if not isinstance(collection, list):
            continue
        for item in collection:
            if not isinstance(item, dict):
                continue
            alias = item.get("alias")
            if not isinstance(alias, str):
                continue
            if valid.fullmatch(alias):
                continue
            normalized = replacements.get(alias)
            if normalized is None:
                base = safe_identifier(alias)
                normalized = base
                suffix = 2
                while normalized in used:
                    normalized = f"{base[:94]}_{suffix}"
                    suffix += 1
                replacements[alias] = normalized
                used.add(normalized)
            item["alias"] = normalized
            if not item.get("displayLabel"):
                item["displayLabel"] = alias.replace("_", " ").strip()
            changed += 1

    if not replacements:
        return
    for field in ("groupBy",):
        values = payload.get(field)
        if isinstance(values, list):
            payload[field] = [replacements.get(value, value) for value in values]
    for field in ("orderBy", "chartHints"):
        values = payload.get(field)
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict):
                continue
            for key in ("column", "categoryColumn", "valueColumn"):
                value = item.get(key)
                if isinstance(value, str):
                    item[key] = replacements.get(value, value)

    def rewrite_having(expression: object) -> None:
        if not isinstance(expression, dict):
            return
        column = expression.get("column")
        if isinstance(column, str):
            expression["column"] = replacements.get(column, column)
        children = expression.get("children")
        if isinstance(children, list):
            for child in children:
                rewrite_having(child)

    rewrite_having(payload.get("having"))
    logger.info("report_order_aliases_normalized count=%s", changed)


def _normalize_between_filters(raw: object) -> None:
    """Normalize common bounded LLM shapes without relaxing the governed contract."""
    if not isinstance(raw, dict):
        return
    payload = raw.get("payload")
    if not isinstance(payload, dict):
        return

    def visit(expression: object) -> None:
        if isinstance(expression, list):
            for child in expression:
                visit(child)
            return
        if not isinstance(expression, dict):
            return
        children = expression.get("children")
        if isinstance(children, list):
            visit(children)
        if expression.get("operator") != "BETWEEN" or expression.get("values") is not None:
            return
        value = expression.get("value")
        bounds: list[object] | None = None
        if isinstance(value, list) and len(value) == 2:
            bounds = value
        elif isinstance(value, dict):
            for lower, upper in (
                ("start", "end"),
                ("from", "to"),
                ("lower", "upper"),
                ("min", "max"),
            ):
                if lower in value and upper in value:
                    bounds = [value[lower], value[upper]]
                    break
        else:
            for lower, upper in (
                ("start", "end"),
                ("from", "to"),
                ("lower", "upper"),
                ("min", "max"),
            ):
                if lower in expression and upper in expression:
                    bounds = [expression.pop(lower), expression.pop(upper)]
                    break
        if bounds is not None:
            expression["values"] = bounds
            expression.pop("value", None)

    visit(payload.get("filters"))
    visit(payload.get("having"))


def _normalize_explicit_temporal_grouping(raw: object) -> None:
    """Make an explicit calendar bucket the selected and grouped output."""
    if not isinstance(raw, dict):
        return
    payload = raw.get("payload")
    if not isinstance(payload, dict):
        return
    temporal_groups = payload.get("temporalGroupBy")
    selected = payload.get("select")
    group_by = payload.get("groupBy")
    if (
        not isinstance(temporal_groups, list)
        or not isinstance(selected, list)
        or not isinstance(group_by, list)
    ):
        return

    for temporal in temporal_groups:
        if not isinstance(temporal, dict):
            continue
        source = temporal.get("column")
        alias = temporal.get("alias")
        if not isinstance(source, str) or not isinstance(alias, str):
            continue
        same_source_groups = [
            item for item in temporal_groups
            if isinstance(item, dict) and item.get("column") == source
        ]
        source_selections = [
            item for item in selected
            if isinstance(item, dict) and item.get("column") == source
        ]
        if len(same_source_groups) != 1 or len(source_selections) != 1:
            continue
        source_selections[0]["alias"] = alias
        if temporal.get("displayLabel"):
            source_selections[0]["displayLabel"] = temporal["displayLabel"]
        payload["groupBy"] = [
            value for value in payload["groupBy"]
            if value != source and value != alias
        ]


def _normalize_implicit_temporal_grouping(
    raw: object,
    request: ReportPlanningRequest,
) -> None:
    """Translate a common LLM-derived calendar alias into the governed contract."""
    if not isinstance(raw, dict):
        return
    payload = raw.get("payload")
    if not isinstance(payload, dict) or payload.get("temporalGroupBy"):
        return
    group_by = payload.get("groupBy")
    selected = payload.get("select")
    if not isinstance(group_by, list) or not isinstance(selected, list):
        return

    authorized_names = {
        column.column_name for column in request.authorized_schema.columns
    }
    temporal_sources = [
        column.column_name
        for column in request.authorized_schema.columns
        if column.data_type.value in {"DATE", "TIMESTAMP"}
    ]
    if len(temporal_sources) != 1:
        return

    granularity_words = {
        "day": "DAY",
        "daily": "DAY",
        "week": "WEEK",
        "weekly": "WEEK",
        "month": "MONTH",
        "monthly": "MONTH",
        "quarter": "QUARTER",
        "quarterly": "QUARTER",
        "year": "YEAR",
        "yearly": "YEAR",
    }
    candidates: list[tuple[str, str]] = []
    for value in group_by:
        if not isinstance(value, str) or value in authorized_names:
            continue
        tokens = set(re.split(r"[^a-z]+", value.lower()))
        matching = {
            granularity
            for word, granularity in granularity_words.items()
            if word in tokens
        }
        if len(matching) == 1:
            candidates.append((value, matching.pop()))
    if len(candidates) != 1:
        return

    alias, granularity = candidates[0]
    matching_select = [
        item for item in selected
        if isinstance(item, dict)
        and (item.get("column") == alias or item.get("alias") == alias)
    ]
    if len(matching_select) != 1:
        return

    source = temporal_sources[0]
    matching_select[0]["column"] = source
    matching_select[0]["alias"] = alias
    payload["groupBy"] = [value for value in group_by if value != alias]
    payload["temporalGroupBy"] = [{
        "column": source,
        "granularity": granularity,
        "alias": alias,
        **(
            {"displayLabel": matching_select[0]["displayLabel"]}
            if matching_select[0].get("displayLabel") else {}
        ),
    }]
    logger.info(
        "report_order_temporal_alias_normalized alias=%s source=%s granularity=%s",
        alias,
        source,
        granularity,
    )


def _normalize_temporal_labels(raw: object, language: str) -> None:
    """Label derived calendar buckets rather than their source timestamp columns."""
    if not isinstance(raw, dict):
        return
    payload = raw.get("payload")
    if not isinstance(payload, dict):
        return
    temporal_groups = payload.get("temporalGroupBy")
    selected = payload.get("select")
    if not isinstance(temporal_groups, list) or not isinstance(selected, list):
        return

    turkish_labels = {
        "DAY": "Gün",
        "WEEK": "Hafta",
        "MONTH": "Ay",
        "QUARTER": "Çeyrek",
        "YEAR": "Yıl",
    }
    for temporal in temporal_groups:
        if not isinstance(temporal, dict):
            continue
        alias = temporal.get("alias")
        granularity = temporal.get("granularity")
        if not isinstance(alias, str) or not isinstance(granularity, str):
            continue
        label = (
            turkish_labels.get(granularity.upper(), alias.replace("_", " ").title())
            if language.lower().startswith("tr")
            else alias.replace("_", " ").title()
        )
        temporal["displayLabel"] = label
        for item in selected:
            if isinstance(item, dict) and item.get("alias") == alias:
                item["displayLabel"] = label


def _normalize_group_by_aliases(raw: object) -> None:
    """Resolve selected presentation aliases back to governed source columns."""
    if not isinstance(raw, dict):
        return
    payload = raw.get("payload")
    if not isinstance(payload, dict):
        return
    selected = payload.get("select")
    group_by = payload.get("groupBy")
    if not isinstance(selected, list) or not isinstance(group_by, list):
        return
    aliases = {
        item["alias"]: item["column"]
        for item in selected
        if isinstance(item, dict)
        and isinstance(item.get("alias"), str)
        and isinstance(item.get("column"), str)
    }
    normalized: list[object] = []
    for value in group_by:
        resolved = aliases.get(value, value)
        if resolved not in normalized:
            normalized.append(resolved)
    payload["groupBy"] = normalized


async def _generate_ml_order(
    provider, request: ReportPlanningRequest, max_preview_rows: int = 100,
    timeout_seconds: int = 7200,
) -> MlOrder:
    registry = {
        f"{problem_type}:{algorithm}": {
            "parameters": {
                name: list(rule) if isinstance(rule, tuple) else sorted(rule)
                for name, rule in definition["parameters"].items()
            },
            "metrics": sorted(definition["metrics"]),
        }
        for (problem_type, algorithm), definition in ALGORITHM_REGISTRY.items()
    }
    base_prompt = (
        f"APPROVED_ALGORITHM_REGISTRY={json.dumps(registry, separators=(',', ':'))}\n"
        f"AUTHORIZED_REQUEST={request.model_dump_json(by_alias=True, exclude_none=True)}\n"
        f"OUTPUT_JSON_SCHEMA={json.dumps(MlOrder.model_json_schema(by_alias=True), separators=(',', ':'))}\n"
        "Return exactly one JSON object matching OUTPUT_JSON_SCHEMA. Do not add request IDs, "
        "planning metadata, alternate version fields, or properties not present in that schema."
    )
    prompt = base_prompt
    last_exception: ValidationError | PlanningValidationError | None = None
    for attempt in range(3):
        raw = await provider.complete_json(ML_SYSTEM_PROMPT, prompt)
        try:
            _enforce_execution_constraints(raw, max_preview_rows, timeout_seconds)
            _remove_unrequested_what_if(raw, request.user_request)
            _remove_implicit_what_if_baseline(raw)
            _normalize_ml_features(raw, request)
            order = MlOrder.model_validate(raw)
            columns = {
                column.column_name: column
                for column in request.authorized_schema.columns
            }
            order.payload.categorical_feature_columns = [
                name for name in order.payload.feature_columns
                if name in columns and columns[name].data_type.value == "STRING"
            ]
            _fit_trial_budget(order)
            if _requires_what_if(request.user_request) and order.payload.what_if_analysis is None:
                raise PlanningValidationError([ValidationIssue(
                    code="WHAT_IF_ANALYSIS_REQUIRED",
                    path="payload.whatIfAnalysis",
                    message=(
                        "The user requested directional management guidance; include bounded "
                        "governed what-if scenarios"
                    ),
                )])
            validate_ml_order(order, request)
            return order
        except (ValidationError, PlanningValidationError) as exception:
            last_exception = exception
            issues = _report_issues(exception)
            logger.warning(
                "ml_order_validation_failed attempt=%s issues=%s",
                attempt + 1,
                [{"code": issue["code"], "path": issue["path"]} for issue in issues],
            )
            prompt = (
                f"{base_prompt}\n"
                f"REJECTED_ORDER={json.dumps(raw, separators=(',', ':'), default=str)}\n"
                f"VALIDATION_ERRORS={json.dumps(issues, separators=(',', ':'))}\n"
                "Regenerate the complete ML order JSON object. Correct every validation "
                "error, use only the approved schema columns and registry values, and keep "
                "all array fields as JSON arrays."
            )
    if last_exception is None:
        raise RuntimeError("ML generation ended without an order")
    raise last_exception


def _fit_trial_budget(order: MlOrder) -> None:
    """Deterministically bound an LLM-proposed Cartesian grid without dropping candidates."""
    selection = order.payload.selection
    candidates = order.payload.candidate_algorithms
    if selection is None or not candidates:
        return
    if selection.maximum_trials < len(candidates):
        selection.maximum_trials = len(candidates)

    def trial_count() -> int:
        return sum(
            max(1, _candidate_trial_count(candidate.parameter_grid))
            for candidate in candidates
        )

    while trial_count() > selection.maximum_trials:
        reducible = [
            (len(values), candidate.algorithm, name, values)
            for candidate in candidates
            for name, values in candidate.parameter_grid.items()
            if len(values) > 1
        ]
        if not reducible:
            break
        _, algorithm, name, values = max(
            reducible, key=lambda item: (item[0], item[1], item[2])
        )
        candidate = next(item for item in candidates if item.algorithm == algorithm)
        candidate.parameter_grid[name] = values[:-1]


def _candidate_trial_count(grid: dict[str, list[object]]) -> int:
    count = 1
    for values in grid.values():
        count *= len(values)
    return count


def _requires_what_if(user_request: str) -> bool:
    return bool(re.search(
        r"\b(?:increase|decrease|raise|reduce|change|adjust|maintain|expand|limit|"
        r"artır\w*|azalt\w*|değiştir\w*|ayarla\w*|sabit\s+tut\w*)\b",
        user_request,
        re.IGNORECASE,
    ))


def _remove_unrequested_what_if(raw: object, user_request: str) -> None:
    """Keep scenario analysis opt-in rather than accepting an LLM invention."""
    if _requires_what_if(user_request) or not isinstance(raw, dict):
        return
    payload = raw.get("payload")
    if isinstance(payload, dict):
        payload.pop("whatIfAnalysis", None)


def _normalize_ml_features(raw: object, request: ReportPlanningRequest) -> None:
    """Drop unsupported or duplicate features without relaxing governed validation."""
    if not isinstance(raw, dict):
        return
    payload = raw.get("payload")
    if not isinstance(payload, dict):
        return
    features = payload.get("featureColumns")
    target = payload.get("targetColumn")
    derivation = payload.get("binaryTargetDerivation")
    derived_source = (
        derivation.get("sourceColumn")
        if isinstance(derivation, dict) else None
    )
    if not isinstance(features, list):
        return
    supported = {
        column.column_name
        for column in request.authorized_schema.columns
        if column.data_type.value in {"INTEGER", "LONG", "DECIMAL", "STRING"}
    }
    normalized: list[str] = []
    for value in features:
        if (
            isinstance(value, str)
            and value in supported
            and value != target
            and value != derived_source
            and value not in normalized
        ):
            normalized.append(value)
    payload["featureColumns"] = normalized


def _remove_implicit_what_if_baseline(raw: object) -> None:
    """Remove only an LLM-emitted baseline that Spark calculates automatically."""
    if not isinstance(raw, dict):
        return
    payload = raw.get("payload")
    if not isinstance(payload, dict):
        return
    analysis = payload.get("whatIfAnalysis")
    if not isinstance(analysis, dict):
        return
    scenarios = analysis.get("scenarios")
    if not isinstance(scenarios, list):
        return

    def is_baseline(item: object) -> bool:
        if not isinstance(item, dict):
            return False
        code = str(item.get("code", "")).upper()
        changes = item.get("changes")
        named_baseline = any(marker in code for marker in (
            "BASELINE", "UNCHANGED", "CONTROL",
        ))
        zero_change = isinstance(changes, list) and (
            not changes or all(
                isinstance(change, dict)
                and isinstance(change.get("percentChange"), (int, float))
                and abs(float(change["percentChange"])) < 0.000001
                for change in changes
            )
        )
        return named_baseline or zero_change

    analysis["scenarios"] = [item for item in scenarios if not is_baseline(item)]


@router.get("/report/schema")
def report_order_schema(x_internal_api_key: str | None = Header(default=None)) -> dict:
    _authenticate(x_internal_api_key)
    return ReportOrder.model_json_schema(by_alias=True)


@router.post("/report", response_model=ReportPlanningResponse)
async def plan_report(
    request: ReportPlanningRequest,
    x_internal_api_key: str | None = Header(default=None),
) -> ReportPlanningResponse:
    _authenticate(x_internal_api_key)
    try:
        effective = await configuration_client.load()
        provider = provider_registry.resolve(effective.llm)
        execution = effective.execution or {}
        max_preview_rows = int(execution.get("maxPreviewRows", 100))
        timeout_seconds = int(execution.get("timeoutSeconds", 7200))
        order = await _generate_report_order(
            provider, request, max_preview_rows, timeout_seconds
        )
        return ReportPlanningResponse(
            request_id=request.request_id, correlation_id=request.correlation_id,
            provider=provider.name, model=provider.model, order=order,
        )
    except ValidationError as exception:
        issues = _report_issues(exception)
        raise HTTPException(status_code=422, detail={"schemaVersion": "1.0",
                            "code": "REPORT_ORDER_INVALID", "issues": issues}) from exception
    except PlanningValidationError as exception:
        raise HTTPException(status_code=422, detail={"schemaVersion": "1.0",
                            "code": "REPORT_ORDER_INVALID",
                            "issues": _report_issues(exception)}) from exception
    except ProviderError as exception:
        raise HTTPException(status_code=503 if exception.retryable else 422,
                            detail={"schemaVersion": "1.0", "code": exception.code,
                                    "retryable": exception.retryable}) from exception


@router.get("/ml/schema")
def ml_order_schema(x_internal_api_key: str | None = Header(default=None)) -> dict:
    _authenticate(x_internal_api_key)
    return MlOrder.model_json_schema(by_alias=True)


@router.post("/ml", response_model=MlPlanningResponse)
async def plan_ml(
    request: ReportPlanningRequest,
    x_internal_api_key: str | None = Header(default=None),
) -> MlPlanningResponse:
    _authenticate(x_internal_api_key)
    try:
        effective = await configuration_client.load()
        provider = provider_registry.resolve(effective.llm)
        execution = effective.execution or {}
        max_preview_rows = int(execution.get("maxPreviewRows", 100))
        timeout_seconds = int(execution.get("timeoutSeconds", 7200))
        order = await _generate_ml_order(
            provider, request, max_preview_rows, timeout_seconds
        )
        return MlPlanningResponse(
            request_id=request.request_id, correlation_id=request.correlation_id,
            provider=provider.name, model=provider.model, order=order)
    except (ValidationError, PlanningValidationError) as exception:
        raise HTTPException(status_code=422, detail={
            "schemaVersion": "1.0", "code": "ML_ORDER_INVALID",
            "issues": _report_issues(exception)}) from exception
    except ProviderError as exception:
        raise HTTPException(status_code=503 if exception.retryable else 422, detail={
            "schemaVersion": "1.0", "code": exception.code,
            "retryable": exception.retryable}) from exception
