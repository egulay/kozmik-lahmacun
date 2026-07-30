import json
import logging
import os
import re
import secrets

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


async def _generate_report_order(provider, request: ReportPlanningRequest) -> ReportOrder:
    base_prompt = build_prompt(request)
    prompt = base_prompt
    last_exception: ValidationError | PlanningValidationError | None = None
    for attempt in range(3):
        raw = await provider.complete_json(SYSTEM_PROMPT, prompt)
        try:
            _normalize_between_filters(raw)
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


async def _generate_ml_order(provider, request: ReportPlanningRequest) -> MlOrder:
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
            _remove_implicit_what_if_baseline(raw)
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
        order = await _generate_report_order(provider, request)
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
        order = await _generate_ml_order(provider, request)
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
