import json
import re
from enum import StrEnum
from typing import Literal

from kozmik_executor.chat.models import ContractModel
from kozmik_executor.execution.management_evidence import (
    DriverEvidence,
    EvidenceScope,
    ManagementEvidence,
    MetricEvidence,
    ModelSelectionEvidence,
    NormalizedComparisonEvidence,
    PopulationScope,
    ReportComparisonEvidence,
    ReportHighlightEvidence,
    ReportMeasureResultEvidence,
    ResultCardinalityEvidence,
    ScenarioEvidence,
    TimeChangeEvidence,
)


class ViolationSeverity(StrEnum):
    BLOCKING = "BLOCKING"
    ADVISORY = "ADVISORY"


class SummaryViolation(ContractModel):
    code: str
    severity: ViolationSeverity
    repair_instruction: str


class SummaryValidation(ContractModel):
    status: Literal["ACCEPTED", "ACCEPTED_WITH_ADVISORIES", "REJECTED"]
    violations: list[SummaryViolation]


class SummaryScope(ContractModel):
    evidence_scopes: list[EvidenceScope]
    population_scopes: list[PopulationScope]
    grouping_dimensions: list[str]
    grouping_values: list[dict[str, int | float | str | bool | None]]
    periods: list[str]
    aggregations: list[str]
    dataset_roles: list[
        Literal[
            "NONE", "VALIDATION_DATA", "UNTOUCHED_TEST_DATA", "SELECTED_MODEL",
            "SCENARIO_COMPARISON",
        ]
    ]
    scenario_codes: list[str]
    selected_models: list[str]
    selection_metrics: list[str]
    metric_codes: list[str]
    metric_averaging_scopes: list[str]


class ManagementSummaryAudit(ContractModel):
    """Service-owned audit metadata for one provider-authored business summary."""

    schema_version: Literal["2.0"] = "2.0"
    language: Literal["en", "tr"]
    prose: str
    evidence_ids: list[str]
    scope: SummaryScope

    def render(self) -> str:
        return self.prose.strip()


class ProviderManagementProse(ContractModel):
    prose: str


EvidenceFact = (
    ResultCardinalityEvidence
    | ReportMeasureResultEvidence
    | ReportComparisonEvidence
    | NormalizedComparisonEvidence
    | TimeChangeEvidence
    | ReportHighlightEvidence
    | MetricEvidence
    | ModelSelectionEvidence
    | DriverEvidence
    | ScenarioEvidence
)


def evidence_index(evidence: ManagementEvidence) -> dict[str, EvidenceFact]:
    facts: list[EvidenceFact] = [evidence.result_cardinality]
    facts.extend(evidence.report_measure_results)
    facts.extend(evidence.report_comparisons)
    facts.extend(evidence.normalized_comparisons)
    facts.extend(evidence.time_changes)
    facts.extend(evidence.report_highlights)
    facts.extend(evidence.metrics)
    if evidence.model_selection is not None:
        facts.append(evidence.model_selection)
    facts.extend(evidence.drivers)
    facts.extend(evidence.scenarios)
    return {fact.evidence_id: fact for fact in facts}


def _dataset_role(fact: EvidenceFact) -> str:
    return {
        EvidenceScope.UNTOUCHED_TEST_DATA: "UNTOUCHED_TEST_DATA",
        EvidenceScope.VALIDATION_DATA_ONLY: "VALIDATION_DATA",
        EvidenceScope.SELECTED_MODEL: "SELECTED_MODEL",
        EvidenceScope.SCENARIO_COMPARISON: "SCENARIO_COMPARISON",
    }.get(fact.scope, "NONE")


def expected_scope(facts: list[EvidenceFact]) -> SummaryScope:
    grouping_dimensions: set[str] = set()
    grouping_values: dict[str, dict[str, int | float | str | bool | None]] = {}
    periods: set[str] = set()
    aggregations: set[str] = set()
    scenario_codes: set[str] = set()
    selected_models: set[str] = set()
    selection_metrics: set[str] = set()
    metric_codes: set[str] = set()
    metric_averaging_scopes: set[str] = set()
    for fact in facts:
        grouping_dimensions.update(getattr(fact, "grouping_dimensions", []))
        measure = getattr(fact, "measure", None)
        if measure is not None and measure.aggregation is not None:
            aggregations.add(measure.aggregation)
        if isinstance(fact, NormalizedComparisonEvidence):
            for normalized_measure in (fact.numerator, fact.denominator):
                if normalized_measure.aggregation is not None:
                    aggregations.add(normalized_measure.aggregation)
        for endpoint_name in ("highest", "lowest", "earlier", "later"):
            endpoint = getattr(fact, endpoint_name, None)
            if endpoint is None:
                continue
            dimensions = endpoint.dimensions
            canonical = json.dumps(dimensions, ensure_ascii=False, sort_keys=True)
            grouping_values[canonical] = dimensions
            periods.update(
                str(value) for value in dimensions.values()
                if isinstance(value, str)
                and re.match(r"^\d{4}-\d{2}(?:-\d{2})?(?:[Tt].*)?$", value)
            )
        if isinstance(fact, ReportHighlightEvidence):
            dimensions = {fact.category_field: fact.leading_category}
            canonical = json.dumps(dimensions, ensure_ascii=False, sort_keys=True)
            grouping_values[canonical] = dimensions
        if isinstance(fact, MetricEvidence):
            metric_codes.add(fact.code)
            if fact.averaging_scope:
                metric_averaging_scopes.add(fact.averaging_scope)
        if isinstance(fact, ScenarioEvidence):
            scenario_codes.add(fact.code)
        if isinstance(fact, ModelSelectionEvidence):
            if fact.selected_algorithm:
                selected_models.add(fact.selected_algorithm)
            if fact.validation_metric:
                selection_metrics.add(fact.validation_metric)
    return SummaryScope(
        evidenceScopes=sorted({fact.scope for fact in facts}, key=str),
        populationScopes=sorted({fact.population_scope for fact in facts}, key=str),
        groupingDimensions=sorted(grouping_dimensions),
        groupingValues=[grouping_values[key] for key in sorted(grouping_values)],
        periods=sorted(periods), aggregations=sorted(aggregations),
        datasetRoles=sorted({_dataset_role(fact) for fact in facts}),
        scenarioCodes=sorted(scenario_codes), selectedModels=sorted(selected_models),
        selectionMetrics=sorted(selection_metrics), metricCodes=sorted(metric_codes),
        metricAveragingScopes=sorted(metric_averaging_scopes),
    )
