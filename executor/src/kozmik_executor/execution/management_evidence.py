import re
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field

from kozmik_executor.chat.models import ContractModel
from kozmik_executor.execution.models import ExecutionCommand
from kozmik_executor.execution.summary_semantics import (
    SemanticKey,
    semantic_definition,
)


class Directionality(StrEnum):
    CONTEXT_DEPENDENT = "CONTEXT_DEPENDENT"
    HIGHER_IS_BETTER = "HIGHER_IS_BETTER"
    LOWER_IS_BETTER = "LOWER_IS_BETTER"
    NEUTRAL = "NEUTRAL"


class RecommendationAuthority(StrEnum):
    NONE = "NONE"
    CONDITIONAL_SCENARIO_ONLY = "CONDITIONAL_SCENARIO_ONLY"


class MeasureSemantics(StrEnum):
    COUNT = "COUNT"
    AGGREGATE_VALUE = "AGGREGATE_VALUE"
    ERROR_MAGNITUDE = "ERROR_MAGNITUDE"
    VARIATION_EXPLAINED = "VARIATION_EXPLAINED"
    CLASSIFICATION_RATE = "CLASSIFICATION_RATE"
    RANKING_SEPARATION = "RANKING_SEPARATION"
    SAMPLE_SIZE = "SAMPLE_SIZE"


class EvidenceScope(StrEnum):
    COMPLETE_RESULT = "COMPLETE_RESULT"
    BOUNDED_CHART_DATA = "BOUNDED_CHART_DATA"
    UNTOUCHED_TEST_DATA = "UNTOUCHED_TEST_DATA"
    VALIDATION_DATA_ONLY = "VALIDATION_DATA_ONLY"
    SELECTED_MODEL = "SELECTED_MODEL"
    SCENARIO_COMPARISON = "SCENARIO_COMPARISON"


class PopulationScope(StrEnum):
    OVERALL = "OVERALL"
    GROUPED = "GROUPED"
    EVALUATED_CASES = "EVALUATED_CASES"
    CANDIDATE_SELECTION = "CANDIDATE_SELECTION"
    SELECTED_MODEL = "SELECTED_MODEL"
    SCENARIO = "SCENARIO"


class MeasureEvidence(ContractModel):
    code: str = Field(max_length=100)
    label: str = Field(max_length=200)
    aggregation: str | None = Field(default=None, max_length=40)
    semantics: MeasureSemantics
    directionality: Directionality
    unit: str | None = Field(default=None, max_length=40)
    semantic_key: SemanticKey


class ComparisonEndpoint(ContractModel):
    dimensions: dict[str, int | float | str | bool | None] = Field(max_length=20)
    value: float


class RelativeSpreadEvidence(ContractModel):
    method: Literal["SYMMETRIC_PERCENT_DIFFERENCE"] = "SYMMETRIC_PERCENT_DIFFERENCE"
    percent: float = Field(ge=0, le=200)
    meaning: Literal["RELATIVE_SPREAD_BETWEEN_HIGHEST_AND_LOWEST"] = (
        "RELATIVE_SPREAD_BETWEEN_HIGHEST_AND_LOWEST"
    )


class ReportComparisonEvidence(ContractModel):
    evidence_id: str = Field(max_length=160)
    scope: Literal[EvidenceScope.COMPLETE_RESULT] = EvidenceScope.COMPLETE_RESULT
    population_scope: Literal[PopulationScope.GROUPED] = PopulationScope.GROUPED
    grouping_dimensions: list[str]
    measure: MeasureEvidence
    highest: ComparisonEndpoint
    lowest: ComparisonEndpoint
    absolute_spread: float = Field(ge=0)
    relative_spread: RelativeSpreadEvidence | None = None
    highest_share_of_total_percent: float | None = Field(default=None, ge=0, le=100)
    highest_tie_count: int = Field(default=1, ge=1)
    lowest_tie_count: int = Field(default=1, ge=1)
    group_count: int = Field(ge=2)


class ReportMeasureResultEvidence(ContractModel):
    evidence_id: str = Field(max_length=160)
    scope: Literal[EvidenceScope.COMPLETE_RESULT] = EvidenceScope.COMPLETE_RESULT
    population_scope: Literal[PopulationScope.OVERALL] = PopulationScope.OVERALL
    measure: MeasureEvidence
    value: float


class NormalizedComparisonEvidence(ContractModel):
    evidence_id: str = Field(max_length=160)
    scope: Literal[EvidenceScope.COMPLETE_RESULT] = EvidenceScope.COMPLETE_RESULT
    population_scope: Literal[PopulationScope.GROUPED] = PopulationScope.GROUPED
    grouping_dimensions: list[str]
    semantic_key: Literal[SemanticKey.NORMALIZED_PER_DENOMINATOR] = (
        SemanticKey.NORMALIZED_PER_DENOMINATOR
    )
    numerator: MeasureEvidence
    denominator: MeasureEvidence
    meaning: Literal["NUMERATOR_PER_DENOMINATOR"] = "NUMERATOR_PER_DENOMINATOR"
    highest: ComparisonEndpoint
    lowest: ComparisonEndpoint
    absolute_spread: float = Field(ge=0)
    relative_spread: RelativeSpreadEvidence | None = None


class ReportHighlightEvidence(ContractModel):
    evidence_id: str = Field(max_length=160)
    scope: Literal[EvidenceScope.BOUNDED_CHART_DATA] = EvidenceScope.BOUNDED_CHART_DATA
    population_scope: Literal[PopulationScope.GROUPED] = PopulationScope.GROUPED
    grouping_dimensions: list[str]
    chart_type: str = Field(max_length=20)
    category_field: str = Field(max_length=100)
    measure: MeasureEvidence
    leading_category: str = Field(max_length=200)
    value: float


class MetricEvidence(ContractModel):
    evidence_id: str = Field(max_length=160)
    scope: Literal[EvidenceScope.UNTOUCHED_TEST_DATA] = EvidenceScope.UNTOUCHED_TEST_DATA
    population_scope: Literal[PopulationScope.EVALUATED_CASES] = (
        PopulationScope.EVALUATED_CASES
    )
    code: str = Field(max_length=100)
    label: str = Field(max_length=200)
    value: float
    unit: Literal["PERCENT", "COUNT"] | str | None = None
    semantics: MeasureSemantics
    directionality: Directionality
    business_definition: str = Field(max_length=500)
    semantic_key: SemanticKey
    averaging_scope: str | None = Field(default=None, max_length=100)


class DriverEvidence(ContractModel):
    evidence_id: str = Field(max_length=160)
    scope: Literal[EvidenceScope.SELECTED_MODEL] = EvidenceScope.SELECTED_MODEL
    population_scope: Literal[PopulationScope.SELECTED_MODEL] = (
        PopulationScope.SELECTED_MODEL
    )
    feature: str = Field(max_length=100)
    importance: float = Field(ge=0)
    direction_known: Literal[False] = False
    causal: Literal[False] = False
    semantic_key: Literal[SemanticKey.FEATURE_IMPORTANCE] = SemanticKey.FEATURE_IMPORTANCE
    importance_method: Literal["TREE_NATIVE"] = "TREE_NATIVE"
    cross_feature_comparable: Literal[True] = True


class ModelSelectionEvidence(ContractModel):
    evidence_id: Literal["ml.model-selection"] = "ml.model-selection"
    scope: Literal[EvidenceScope.VALIDATION_DATA_ONLY] = (
        EvidenceScope.VALIDATION_DATA_ONLY
    )
    population_scope: Literal[PopulationScope.CANDIDATE_SELECTION] = (
        PopulationScope.CANDIDATE_SELECTION
    )
    semantic_key: Literal[SemanticKey.VALIDATION_SCORE] = SemanticKey.VALIDATION_SCORE
    selected_algorithm: str | None = Field(default=None, max_length=100)
    candidate_algorithms_evaluated: int | None = Field(default=None, ge=1)
    tuning_trials_evaluated: int | None = Field(default=None, ge=1)
    validation_metric: str | None = Field(default=None, max_length=100)
    validation_score: float | None = None
    validation_score_unit: Literal["PERCENT"] | str | None = None
    selection_basis: Literal["VALIDATION_DATA_ONLY"] = "VALIDATION_DATA_ONLY"
    final_metrics_scope: Literal["UNTOUCHED_TEST_DATA"] = "UNTOUCHED_TEST_DATA"


class ScenarioChangeEvidence(ContractModel):
    column: str = Field(max_length=100)
    percent_change: float = Field(ge=-25, le=25)


class ScenarioEvidence(ContractModel):
    evidence_id: str = Field(max_length=160)
    scope: Literal[EvidenceScope.SCENARIO_COMPARISON] = (
        EvidenceScope.SCENARIO_COMPARISON
    )
    population_scope: Literal[PopulationScope.SCENARIO] = PopulationScope.SCENARIO
    semantic_key: Literal[SemanticKey.SCENARIO_DELTA] = SemanticKey.SCENARIO_DELTA
    code: str = Field(max_length=50)
    changes: list[ScenarioChangeEvidence] = Field(min_length=1, max_length=3)
    baseline_prediction: float | None = None
    scenario_prediction: float | None = None
    delta: float | None = None
    delta_percent: float
    causal: Literal[False] = False


class TimeChangeEvidence(ContractModel):
    evidence_id: str = Field(max_length=160)
    scope: Literal[EvidenceScope.COMPLETE_RESULT] = EvidenceScope.COMPLETE_RESULT
    population_scope: Literal[PopulationScope.OVERALL] = PopulationScope.OVERALL
    grouping_dimensions: list[str]
    semantic_key: Literal[SemanticKey.TIME_PERCENTAGE_CHANGE] = (
        SemanticKey.TIME_PERCENTAGE_CHANGE
    )
    measure: MeasureEvidence
    earlier: ComparisonEndpoint
    later: ComparisonEndpoint
    absolute_change: float
    percentage_change: float | None = None
    method: Literal["LATER_MINUS_EARLIER_OVER_ABSOLUTE_EARLIER"] = (
        "LATER_MINUS_EARLIER_OVER_ABSOLUTE_EARLIER"
    )


class ResultCardinalityEvidence(ContractModel):
    evidence_id: Literal["result.row-count"] = "result.row-count"
    scope: Literal[EvidenceScope.COMPLETE_RESULT] = EvidenceScope.COMPLETE_RESULT
    population_scope: Literal[PopulationScope.OVERALL] = PopulationScope.OVERALL
    semantic_key: Literal[SemanticKey.RESULT_CARDINALITY] = SemanticKey.RESULT_CARDINALITY
    value: int = Field(ge=0)


class EvidencePolicy(ContractModel):
    contains_raw_rows: Literal[False] = False
    report_directionality: Literal["CONTEXT_DEPENDENT"] = "CONTEXT_DEPENDENT"
    recommendation_authority: RecommendationAuthority
    authorized_scenario_code: str | None = Field(default=None, max_length=50)
    warnings_rendered_separately: Literal[True] = True
    units_must_be_explicit: Literal[True] = True
    driver_direction_known: Literal[False] = False
    causal_claims_allowed: Literal[False] = False


class ApprovedWarning(ContractModel):
    code: str = Field(max_length=100)
    message_key: str | None = Field(default=None, max_length=200)


class ManagementEvidence(ContractModel):
    schema_version: Literal["2.0"] = "2.0"
    semantic_registry_version: Literal["1.0"] = "1.0"
    execution_type: Literal["REPORT", "ML"]
    language: Literal["tr", "en"]
    objective: str = Field(max_length=2000)
    result_row_count: int = Field(ge=0)
    result_cardinality: ResultCardinalityEvidence
    problem_type: str | None = Field(default=None, max_length=100)
    target: str | None = Field(default=None, max_length=100)
    feature_columns: list[str] = Field(default_factory=list)
    report_measure_results: list[ReportMeasureResultEvidence] = Field(
        default_factory=list, max_length=20
    )
    report_comparisons: list[ReportComparisonEvidence] = Field(
        default_factory=list, max_length=10
    )
    normalized_comparisons: list[NormalizedComparisonEvidence] = Field(
        default_factory=list, max_length=10
    )
    time_changes: list[TimeChangeEvidence] = Field(default_factory=list, max_length=10)
    report_highlights: list[ReportHighlightEvidence] = Field(
        default_factory=list, max_length=10
    )
    report_breakdown: list[dict[str, int | float | str | bool | None]] = Field(
        default_factory=list
    )
    metrics: list[MetricEvidence] = Field(default_factory=list, max_length=20)
    model_selection: ModelSelectionEvidence | None = None
    drivers: list[DriverEvidence] = Field(default_factory=list, max_length=10)
    scenario_objective: Literal["MAXIMIZE_TARGET", "MINIMIZE_TARGET"] | None = None
    scenarios: list[ScenarioEvidence] = Field(default_factory=list, max_length=6)
    warnings: list[ApprovedWarning] = Field(default_factory=list, max_length=20)
    policy: EvidencePolicy


_SENSITIVE_DIMENSION = re.compile(
    r"(?:^|_)(?:id|uuid|email|phone|mobile|address|name|subscriber|customer|account)(?:$|_)",
    re.IGNORECASE,
)


def numeric_value(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return float(number) if number.is_finite() else None


def safe_dimensions(values: object) -> dict[str, int | float | str | bool | None]:
    if not isinstance(values, dict):
        return {}
    return {
        str(key): value
        for key, value in values.items()
        if not _SENSITIVE_DIMENSION.search(str(key))
        and isinstance(value, (int, float, str, bool, type(None)))
    }


class ManagementEvidenceBuilder:
    def build(
        self, command: ExecutionCommand, result: dict[str, Any],
    ) -> ManagementEvidence:
        language = "tr" if command.order.requested_language.lower().startswith("tr") else "en"
        report_measures = self._report_measures(command)
        measure_results = self._report_measure_results(result, report_measures)
        comparisons = self._report_comparisons(result, report_measures)
        normalized = self._normalized_comparisons(result, report_measures)
        time_changes = self._time_changes(result, report_measures)
        highlights = self._report_highlights(result, report_measures)
        breakdown = self._report_breakdown(command, result)
        metrics = self._metrics(result, language) if command.execution_type == "ML" else []
        model_selection = (
            self._model_selection(result) if command.execution_type == "ML" else None
        )
        drivers = self._drivers(result) if command.execution_type == "ML" else []
        scenario_objective, scenarios = self._scenarios(result)
        authorized_scenario = None
        if scenarios and scenario_objective:
            authorized_scenario = (
                max(scenarios, key=lambda item: item.delta_percent)
                if scenario_objective == "MAXIMIZE_TARGET"
                else min(scenarios, key=lambda item: item.delta_percent)
            )
        warnings = [
            ApprovedWarning.model_validate({
                "code": item.get("code"), "messageKey": item.get("messageKey"),
            })
            for item in result.get("warnings", [])[:20]
            if isinstance(item, dict)
            and isinstance(item.get("code"), str)
            and item.get("code") != "RESULT_TRUNCATED"
        ]
        return ManagementEvidence(
            executionType=command.execution_type,
            language=language,
            objective=command.order.request_summary[:2000],
            resultRowCount=int(result.get("rowCount", 0)),
            resultCardinality={"value": int(result.get("rowCount", 0))},
            problemType=(
                command.order.payload.problem_type
                if command.execution_type == "ML" else None
            ),
            target=(
                command.order.payload.target_column
                if command.execution_type == "ML"
                and not _SENSITIVE_DIMENSION.search(command.order.payload.target_column)
                else None
            ),
            featureColumns=(
                [
                    column for column in command.order.payload.feature_columns
                    if not _SENSITIVE_DIMENSION.search(column)
                ]
                if command.execution_type == "ML" else []
            ),
            reportMeasureResults=measure_results,
            reportComparisons=comparisons,
            normalizedComparisons=normalized,
            timeChanges=time_changes,
            reportHighlights=highlights,
            reportBreakdown=breakdown,
            metrics=metrics,
            modelSelection=model_selection,
            drivers=drivers,
            scenarioObjective=scenario_objective,
            scenarios=scenarios,
            warnings=warnings,
            policy=EvidencePolicy(
                recommendationAuthority=(
                    RecommendationAuthority.CONDITIONAL_SCENARIO_ONLY
                    if scenarios else RecommendationAuthority.NONE
                ),
                authorizedScenarioCode=(
                    authorized_scenario.code if authorized_scenario else None
                ),
            ),
        )

    @staticmethod
    def _report_breakdown(
        command: ExecutionCommand, result: dict[str, Any],
    ) -> list[dict[str, int | float | str | bool | None]]:
        if command.execution_type != "REPORT":
            return []
        summary_facts = result.get("summaryFacts")
        supplied = summary_facts.get("reportBreakdown") if isinstance(
            summary_facts, dict
        ) else None
        if not isinstance(supplied, list):
            return []
        allowed = {
            *(item.alias for item in command.order.payload.aggregations),
            *(
                f"{item.alias}ShareOfTotalPercent"
                for item in command.order.payload.aggregations
                if item.function.value in {"SUM", "COUNT"}
            ),
            *(
                field for field in command.order.payload.group_by
                if not _SENSITIVE_DIMENSION.search(field)
            ),
            *(
                item.alias for item in command.order.payload.temporal_group_by
                if not _SENSITIVE_DIMENSION.search(item.alias)
            ),
        }
        return [
            {
                str(key): value
                for key, value in row.items()
                if key in allowed
                and isinstance(value, (int, float, str, bool, type(None)))
            }
            for row in supplied
            if isinstance(row, dict)
        ]

    @staticmethod
    def _report_measures(command: ExecutionCommand) -> dict[str, MeasureEvidence]:
        if command.execution_type != "REPORT":
            return {}
        return {
            item.alias: MeasureEvidence(
                code=item.alias,
                label=item.display_label or item.alias.replace("_", " ").title(),
                aggregation=item.function.value,
                semantics=(
                    MeasureSemantics.COUNT
                    if item.function.value in {"COUNT", "COUNT_DISTINCT"}
                    else MeasureSemantics.AGGREGATE_VALUE
                ),
                directionality=Directionality.CONTEXT_DEPENDENT,
                unit=None,
                semanticKey=SemanticKey(item.function.value),
            )
            for item in command.order.payload.aggregations
        }

    @staticmethod
    def _report_comparisons(
        result: dict[str, Any], measures: dict[str, MeasureEvidence],
    ) -> list[ReportComparisonEvidence]:
        internal = result.get("summaryFacts")
        supplied = internal.get("reportComparisons") if isinstance(internal, dict) else None
        if not isinstance(internal, dict) or internal.get("schemaVersion") != "2.0":
            return []
        if not isinstance(supplied, list):
            return []
        approved = []
        for item in supplied[:10]:
            if not isinstance(item, dict):
                continue
            code = item.get("measure")
            measure = measures.get(code)
            if measure is None:
                continue
            highest = item.get("highest")
            lowest = item.get("lowest")
            if not isinstance(highest, dict) or not isinstance(lowest, dict):
                continue
            high_value = numeric_value(highest.get("value"))
            low_value = numeric_value(lowest.get("value"))
            absolute = numeric_value(item.get("absoluteSpread", item.get("absoluteDifference")))
            group_count = item.get("groupCount")
            if high_value is None or low_value is None or absolute is None:
                continue
            if not isinstance(group_count, int) or group_count < 2:
                continue
            spread = item.get("relativeSpread")
            spread_value = (
                numeric_value(spread.get("percent"))
                if isinstance(spread, dict)
                else None
            )
            approved.append(ReportComparisonEvidence(
                evidenceId=f"report.comparison.{code}",
                measure=measure,
                groupingDimensions=sorted({
                    *safe_dimensions(highest.get("dimensions")).keys(),
                    *safe_dimensions(lowest.get("dimensions")).keys(),
                }),
                highest={
                    "dimensions": safe_dimensions(highest.get("dimensions")),
                    "value": high_value,
                },
                lowest={
                    "dimensions": safe_dimensions(lowest.get("dimensions")),
                    "value": low_value,
                },
                absoluteSpread=absolute,
                relativeSpread=(
                    RelativeSpreadEvidence(percent=max(0.0, min(200.0, spread_value)))
                    if spread_value is not None else None
                ),
                highestShareOfTotalPercent=numeric_value(
                    item.get("highestShareOfTotalPercent", item.get("highestSharePercent"))
                ),
                highestTieCount=(
                    item.get("highestTieCount")
                    if isinstance(item.get("highestTieCount"), int)
                    and item["highestTieCount"] >= 1 else 1
                ),
                lowestTieCount=(
                    item.get("lowestTieCount")
                    if isinstance(item.get("lowestTieCount"), int)
                    and item["lowestTieCount"] >= 1 else 1
                ),
                groupCount=group_count,
            ))
        return approved

    @staticmethod
    def _report_measure_results(
        result: dict[str, Any], measures: dict[str, MeasureEvidence],
    ) -> list[ReportMeasureResultEvidence]:
        internal = result.get("summaryFacts")
        supplied = internal.get("reportMeasures") if isinstance(internal, dict) else None
        if not isinstance(internal, dict) or internal.get("schemaVersion") != "2.0":
            return []
        if not isinstance(supplied, list):
            return []
        approved = []
        for item in supplied[:20]:
            if not isinstance(item, dict):
                continue
            measure = measures.get(item.get("measure"))
            value = numeric_value(item.get("value"))
            if measure is None or value is None:
                continue
            approved.append(ReportMeasureResultEvidence(
                evidenceId=f"report.measure.{measure.code}",
                measure=measure,
                value=value,
            ))
        return approved

    @staticmethod
    def _normalized_comparisons(
        result: dict[str, Any], measures: dict[str, MeasureEvidence],
    ) -> list[NormalizedComparisonEvidence]:
        internal = result.get("summaryFacts")
        supplied = (
            internal.get("normalizedComparisons") if isinstance(internal, dict) else None
        )
        if not isinstance(internal, dict) or internal.get("schemaVersion") != "2.0":
            return []
        if not isinstance(supplied, list):
            return []
        approved = []
        for item in supplied[:10]:
            if not isinstance(item, dict):
                continue
            numerator = measures.get(item.get("numeratorMeasure"))
            denominator = measures.get(item.get("denominatorMeasure"))
            highest = item.get("highest")
            lowest = item.get("lowest")
            if numerator is None or denominator is None:
                continue
            if not isinstance(highest, dict) or not isinstance(lowest, dict):
                continue
            high_value = numeric_value(highest.get("value"))
            low_value = numeric_value(lowest.get("value"))
            absolute = numeric_value(item.get("absoluteSpread"))
            spread = item.get("relativeSpread")
            spread_value = (
                numeric_value(spread.get("percent")) if isinstance(spread, dict) else None
            )
            if high_value is None or low_value is None or absolute is None:
                continue
            approved.append(NormalizedComparisonEvidence(
                evidenceId=(
                    f"report.normalized.{numerator.code}.per.{denominator.code}"
                ),
                numerator=numerator,
                denominator=denominator,
                groupingDimensions=sorted({
                    *safe_dimensions(highest.get("dimensions")).keys(),
                    *safe_dimensions(lowest.get("dimensions")).keys(),
                }),
                highest={
                    "dimensions": safe_dimensions(highest.get("dimensions")),
                    "value": high_value,
                },
                lowest={
                    "dimensions": safe_dimensions(lowest.get("dimensions")),
                    "value": low_value,
                },
                absoluteSpread=absolute,
                relativeSpread=(
                    RelativeSpreadEvidence(percent=max(0.0, min(200.0, spread_value)))
                    if spread_value is not None else None
                ),
            ))
        return approved

    @staticmethod
    def _time_changes(
        result: dict[str, Any], measures: dict[str, MeasureEvidence],
    ) -> list[TimeChangeEvidence]:
        internal = result.get("summaryFacts")
        supplied = internal.get("timeChanges") if isinstance(internal, dict) else None
        if not isinstance(internal, dict) or internal.get("schemaVersion") != "2.0":
            return []
        if not isinstance(supplied, list):
            return []
        approved = []
        for item in supplied[:10]:
            if not isinstance(item, dict):
                continue
            measure = measures.get(item.get("measure"))
            earlier = item.get("earlier")
            later = item.get("later")
            if measure is None or not isinstance(earlier, dict) or not isinstance(later, dict):
                continue
            earlier_value = numeric_value(earlier.get("value"))
            later_value = numeric_value(later.get("value"))
            absolute_change = numeric_value(item.get("absoluteChange"))
            percentage_change = numeric_value(item.get("percentageChange"))
            if earlier_value is None or later_value is None or absolute_change is None:
                continue
            earlier_dimensions = safe_dimensions(earlier.get("dimensions"))
            later_dimensions = safe_dimensions(later.get("dimensions"))
            grouping_dimensions = sorted({
                *earlier_dimensions.keys(), *later_dimensions.keys(),
            })
            if not grouping_dimensions:
                continue
            approved.append(TimeChangeEvidence(
                evidenceId=f"report.time-change.{measure.code}.{len(approved) + 1}",
                groupingDimensions=grouping_dimensions,
                measure=measure,
                earlier={"dimensions": earlier_dimensions, "value": earlier_value},
                later={"dimensions": later_dimensions, "value": later_value},
                absoluteChange=absolute_change,
                percentageChange=percentage_change,
            ))
        return approved

    @staticmethod
    def _report_highlights(
        result: dict[str, Any], measures: dict[str, MeasureEvidence],
    ) -> list[ReportHighlightEvidence]:
        approved = []
        for index, chart in enumerate(result.get("charts", [])[:10]):
            if not isinstance(chart, dict):
                continue
            categories = chart.get("categories")
            series = chart.get("series")
            category_field = chart.get("categoryField")
            measure = measures.get(chart.get("valueField"))
            chart_type = chart.get("type")
            if (not isinstance(categories, list) or not isinstance(series, list)
                    or not isinstance(category_field, str)
                    or not isinstance(chart_type, str) or measure is None):
                continue
            totals = [0.0 for _ in categories]
            found = False
            for series_item in series:
                data = series_item.get("data") if isinstance(series_item, dict) else None
                if not isinstance(data, list):
                    continue
                for position, value in enumerate(data[:len(categories)]):
                    number = numeric_value(value)
                    if number is not None:
                        totals[position] += number
                        found = True
            if not found or not totals:
                continue
            leading = max(range(len(totals)), key=totals.__getitem__)
            category = categories[leading]
            if category is None or _SENSITIVE_DIMENSION.search(category_field):
                continue
            approved.append(ReportHighlightEvidence(
                evidenceId=f"report.highlight.{index + 1}.{measure.code}",
                chartType=chart_type,
                categoryField=category_field,
                groupingDimensions=[category_field],
                measure=measure,
                leadingCategory=str(category),
                value=totals[leading],
            ))
        return approved

    @staticmethod
    def _metrics(result: dict[str, Any], language: str = "en") -> list[MetricEvidence]:
        definitions: dict[
            str, tuple[str, SemanticKey, MeasureSemantics, Directionality, bool, str | None]
        ] = {
            "MAE": ("Average absolute prediction difference", SemanticKey.MAE,
                    MeasureSemantics.ERROR_MAGNITUDE, Directionality.LOWER_IS_BETTER,
                    False, None),
            "RMSE": ("Larger-error-sensitive prediction difference", SemanticKey.RMSE,
                     MeasureSemantics.ERROR_MAGNITUDE, Directionality.LOWER_IS_BETTER,
                     False, None),
            "R2": ("Observed variation captured", SemanticKey.R2,
                   MeasureSemantics.VARIATION_EXPLAINED, Directionality.HIGHER_IS_BETTER,
                   True, None),
            "ACCURACY": ("Overall evaluated-case correctness", SemanticKey.ACCURACY,
                         MeasureSemantics.CLASSIFICATION_RATE,
                         Directionality.HIGHER_IS_BETTER, True, "ALL_CLASSES"),
            "CORRECT_PREDICTION_RATE": (
                "Overall evaluated-case correctness", SemanticKey.ACCURACY,
                MeasureSemantics.CLASSIFICATION_RATE, Directionality.HIGHER_IS_BETTER,
                False, "ALL_CLASSES"),
            "AUC": ("Ranking separation", SemanticKey.AUC,
                    MeasureSemantics.RANKING_SEPARATION, Directionality.HIGHER_IS_BETTER,
                    True, "POSITIVE_CLASS"),
            "F1": ("Class-frequency-weighted precision-recall balance", SemanticKey.F1,
                   MeasureSemantics.CLASSIFICATION_RATE, Directionality.HIGHER_IS_BETTER,
                   True, "WEIGHTED_ACROSS_CLASSES"),
            "PRECISION": ("Class-frequency-weighted precision", SemanticKey.PRECISION,
                          MeasureSemantics.CLASSIFICATION_RATE,
                          Directionality.HIGHER_IS_BETTER, True,
                          "WEIGHTED_ACROSS_CLASSES"),
            "RECALL": ("Class-frequency-weighted recall", SemanticKey.RECALL,
                       MeasureSemantics.CLASSIFICATION_RATE,
                       Directionality.HIGHER_IS_BETTER, True,
                       "WEIGHTED_ACROSS_CLASSES"),
            "POSITIVE_PRECISION": ("Flagged positive-case correctness", SemanticKey.PRECISION,
                                   MeasureSemantics.CLASSIFICATION_RATE,
                                   Directionality.HIGHER_IS_BETTER, False,
                                   "POSITIVE_CLASS"),
            "POSITIVE_RECALL": ("Positive-case coverage", SemanticKey.RECALL,
                                MeasureSemantics.CLASSIFICATION_RATE,
                                Directionality.HIGHER_IS_BETTER, False,
                                "POSITIVE_CLASS"),
            "SPECIFICITY": ("Negative-case exclusion", SemanticKey.SPECIFICITY,
                            MeasureSemantics.CLASSIFICATION_RATE,
                            Directionality.HIGHER_IS_BETTER, False,
                            "NEGATIVE_CLASS"),
            "ACTUAL_POSITIVE_RATE": ("Actual positive-case share", SemanticKey.ACTUAL_RATE,
                                     MeasureSemantics.CLASSIFICATION_RATE,
                                     Directionality.NEUTRAL, False, "ACTUAL_POSITIVE_CLASS"),
            "BASELINE_ACCURACY": ("Simple majority baseline", SemanticKey.BASELINE_ACCURACY,
                                  MeasureSemantics.CLASSIFICATION_RATE,
                                  Directionality.NEUTRAL, False, "ALL_CLASSES"),
            "TEST_CASE_COUNT": ("Evaluated cases", SemanticKey.SAMPLE_COUNT,
                                MeasureSemantics.SAMPLE_SIZE, Directionality.NEUTRAL,
                                False, None),
            "AVERAGE_POSITIVE_PROBABILITY": (
                "Average positive-class model score", SemanticKey.AVERAGE_MODEL_SCORE,
                MeasureSemantics.CLASSIFICATION_RATE, Directionality.NEUTRAL,
                False, "POSITIVE_CLASS"),
            "PREDICTED_POSITIVE_RATE": (
                "Cases flagged positive", SemanticKey.PREDICTED_RATE,
                MeasureSemantics.CLASSIFICATION_RATE, Directionality.NEUTRAL,
                False, "PREDICTED_POSITIVE_CLASS"),
        }
        turkish_labels = {
            "MAE": "Ortalama mutlak tahmin farkı",
            "RMSE": "Büyük hatalara duyarlı tahmin farkı",
            "R2": "Açıklanan gözlem değişkenliği",
            "ACCURACY": "Genel değerlendirme doğruluğu",
            "CORRECT_PREDICTION_RATE": "Genel değerlendirme doğruluğu",
            "AUC": "Sıralama ayırt ediciliği",
            "F1": "Sınıf ağırlıklı kesinlik ve kapsama dengesi",
            "PRECISION": "Sınıf ağırlıklı kesinlik",
            "RECALL": "Sınıf ağırlıklı kapsama",
            "POSITIVE_PRECISION": "İşaretlenen olumlu durumların doğruluğu",
            "POSITIVE_RECALL": "Olumlu durumların kapsanması",
            "SPECIFICITY": "Olumsuz durumların dışlanması",
            "ACTUAL_POSITIVE_RATE": "Gerçek olumlu durum oranı",
            "BASELINE_ACCURACY": "Basit çoğunluk karşılaştırması",
            "TEST_CASE_COUNT": "Değerlendirilen durumlar",
            "AVERAGE_POSITIVE_PROBABILITY": "Ortalama olumlu sınıf model puanı",
            "PREDICTED_POSITIVE_RATE": "Olumlu olarak işaretlenen durumlar",
        }
        approved = []
        seen = set()
        available_codes = {
            item.get("code") for item in result.get("kpis", [])
            if isinstance(item, dict)
        }
        for item in result.get("kpis", [])[:30]:
            if not isinstance(item, dict):
                continue
            code = item.get("code")
            if code == "CORRECT_PREDICTION_RATE" and "ACCURACY" in available_codes:
                continue
            definition = definitions.get(code)
            value = numeric_value(item.get("value"))
            if definition is None or value is None or code in seen:
                continue
            label, semantic_key, semantics, directionality, fraction, averaging_scope = definition
            if language == "tr":
                label = turkish_labels[code]
            if fraction:
                value *= 100
            unit = "COUNT" if semantics == MeasureSemantics.SAMPLE_SIZE else (
                "PERCENT" if semantics in {
                    MeasureSemantics.CLASSIFICATION_RATE,
                    MeasureSemantics.RANKING_SEPARATION,
                    MeasureSemantics.VARIATION_EXPLAINED,
                } else item.get("unit")
            )
            approved.append(MetricEvidence(
                evidenceId=f"ml.metric.{code}.test", code=code, label=label,
                value=value, unit=unit,
                semantics=semantics, directionality=directionality,
                semanticKey=semantic_key,
                businessDefinition=semantic_definition(semantic_key).canonical_business_meaning,
                averagingScope=averaging_scope,
            ))
            seen.add(code)
        return approved

    @staticmethod
    def _model_selection(result: dict[str, Any]) -> ModelSelectionEvidence | None:
        values = {
            item.get("code"): item
            for item in result.get("kpis", [])
            if isinstance(item, dict) and isinstance(item.get("code"), str)
        }
        selected = values.get("SELECTED_ALGORITHM", {}).get("value")
        candidates = numeric_value(
            values.get("CANDIDATE_ALGORITHMS_EVALUATED", {}).get("value")
        )
        trials = numeric_value(values.get("TUNING_TRIALS_EVALUATED", {}).get("value"))
        validation = values.get("BEST_VALIDATION_SCORE", {})
        validation_score = numeric_value(validation.get("value"))
        validation_metric = validation.get("unit")
        if not any((selected, candidates, trials, validation_score is not None)):
            return None
        percentage_metric = validation_metric in {
            "R2", "ACCURACY", "PRECISION", "RECALL", "F1", "AUC",
        }
        if validation_score is not None and percentage_metric:
            validation_score *= 100
        return ModelSelectionEvidence(
            selectedAlgorithm=selected if isinstance(selected, str) else None,
            candidateAlgorithmsEvaluated=int(candidates) if candidates else None,
            tuningTrialsEvaluated=int(trials) if trials else None,
            validationMetric=(
                validation_metric if isinstance(validation_metric, str) else None
            ),
            validationScore=validation_score,
            validationScoreUnit="PERCENT" if percentage_metric else None,
        )

    @staticmethod
    def _drivers(result: dict[str, Any]) -> list[DriverEvidence]:
        for chart in result.get("charts", [])[:10]:
            if not isinstance(chart, dict) or chart.get("chartId") != "feature-importance":
                continue
            categories = chart.get("categories")
            series = chart.get("series")
            if (not isinstance(categories, list) or not isinstance(series, list)
                    or not series or not isinstance(series[0], dict)
                    or not isinstance(series[0].get("data"), list)):
                return []
            grouped: dict[str, float] = {}
            for feature, importance in zip(
                categories[:100], series[0]["data"][:100], strict=False
            ):
                value = numeric_value(importance)
                if not isinstance(feature, str) or value is None or value < 0:
                    continue
                source = feature.split(":", 1)[0].strip()
                if _SENSITIVE_DIMENSION.search(source):
                    continue
                grouped[source] = grouped.get(source, 0.0) + value
            return sorted(
                [DriverEvidence(
                    evidenceId=f"ml.driver.{index + 1}",
                    feature=key,
                    importance=value,
                )
                 for index, (key, value) in enumerate(grouped.items())
                ],
                key=lambda item: item.importance,
                reverse=True,
            )[:10]
        return []

    @staticmethod
    def _scenarios(
        result: dict[str, Any],
    ) -> tuple[str | None, list[ScenarioEvidence]]:
        for chart in result.get("charts", [])[:5]:
            if not isinstance(chart, dict) or chart.get("chartId") != "what-if-analysis":
                continue
            objective = chart.get("objective")
            if objective not in {"MAXIMIZE_TARGET", "MINIMIZE_TARGET"}:
                return None, []
            approved = []
            for item in chart.get("scenarioFacts", [])[:6]:
                if not isinstance(item, dict) or not isinstance(item.get("code"), str):
                    continue
                changes = [
                    ScenarioChangeEvidence.model_validate(change)
                    for change in item.get("changes", [])[:3]
                    if isinstance(change, dict)
                    and isinstance(change.get("column"), str)
                    and not _SENSITIVE_DIMENSION.search(change["column"])
                ]
                delta_percent = numeric_value(item.get("deltaPercent"))
                if not changes or delta_percent is None:
                    continue
                approved.append(ScenarioEvidence(
                    evidenceId=f"ml.scenario.{item['code']}",
                    code=item["code"], changes=changes,
                    baselinePrediction=numeric_value(item.get("baselinePrediction")),
                    scenarioPrediction=numeric_value(item.get("scenarioPrediction")),
                    delta=numeric_value(item.get("delta")),
                    deltaPercent=delta_percent,
                ))
            return objective, approved
        return None, []
