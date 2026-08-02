import asyncio
import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from kozmik_executor.chat.providers import ProviderError
from kozmik_executor.execution.explanation import (
    ManagementSummaryValidator,
    ResultExplainer,
)
from kozmik_executor.execution.management_evidence import (
    ManagementEvidence,
    ManagementEvidenceBuilder,
    RecommendationAuthority,
)
from kozmik_executor.execution.management_summary import (
    evidence_index,
    expected_scope,
)
from kozmik_executor.execution.models import ExecutionCommand
from kozmik_executor.execution.summary_semantics import (
    SEMANTIC_REGISTRY,
    SemanticKey,
)


def report_command(language: str = "en", scalar: bool = False) -> ExecutionCommand:
    entity_id = uuid4()
    payload = {
        "select": [{"column": "region", "displayLabel": "Region"}],
        "filters": [],
        "groupBy": ["region"],
        "aggregations": [
            {
                "function": "COUNT", "column": None, "alias": "call_count",
                "displayLabel": "Call count",
            },
            {
                "function": "SUM", "column": "charge", "alias": "total_charge",
                "displayLabel": "Total charge",
            },
        ],
        "orderBy": [{"column": "total_charge", "direction": "DESC"}],
        "limit": 100,
        "chartHints": [],
    }
    if scalar:
        payload["select"] = [{"column": "charge", "displayLabel": "Charge"}]
        payload["groupBy"] = []
        payload["aggregations"] = [{
            "function": "SUM", "column": "charge", "alias": "total_charge",
            "displayLabel": "Total charge",
        }]
        payload["orderBy"] = []
    return ExecutionCommand.model_validate({
        "schemaVersion": "1.0", "eventId": str(uuid4()),
        "correlationId": "summary-test", "executionId": str(uuid4()),
        "entityId": str(entity_id), "actorUserId": str(uuid4()),
        "occurredAt": datetime.now(timezone.utc).isoformat(),
        "executionType": "REPORT", "authorization": {"roles": ["REPORTER"]},
        "configuration": {"llm": {
            "provider": "MOCK", "baseUrl": "http://unused", "model": "mock",
            "timeoutSeconds": 10, "maxRetries": 0, "maxContextMessages": 10,
            "maxContextCharacters": 1000,
        }},
        "order": {
            "schemaVersion": "1.0", "executionType": "REPORT",
            "entityId": str(entity_id), "requestedLanguage": language,
            "requestSummary": "Compare call count and total charge by region.",
            "constraints": {"maxPreviewRows": 100, "timeoutSeconds": 300},
            "payload": payload,
        },
    })


def ml_command(language: str = "en", scenarios: bool = False) -> ExecutionCommand:
    entity_id = uuid4()
    payload = {
        "problemType": "BINARY_CLASSIFICATION",
        "algorithm": "LOGISTIC_REGRESSION",
        "targetColumn": "long_call",
        "binaryTargetDerivation": {
            "sourceColumn": "duration_seconds", "operator": "GT", "threshold": 300,
        },
        "featureColumns": ["call_type", "origin_region", "duration_seconds"],
        "categoricalFeatureColumns": ["call_type", "origin_region"],
        "filters": [],
        "split": {"strategy": "RANDOM", "trainingRatio": 0.7, "seed": 42},
        "parameters": {},
        "candidateAlgorithms": [
            {"algorithm": "LOGISTIC_REGRESSION", "parameterGrid": {"maxIter": [10]}},
            {"algorithm": "DECISION_TREE_CLASSIFIER", "parameterGrid": {"maxDepth": [3]}},
        ],
        "selection": {
            "strategy": "TRAIN_VALIDATION_SPLIT", "primaryMetric": "AUC",
            "maximumTrials": 20, "trainingRatio": 0.7,
            "validationRatio": 0.15, "testRatio": 0.15, "seed": 42,
        },
        "metrics": ["ACCURACY", "AUC", "F1"],
        "output": {"includeFeatureImportance": True,
                   "includePredictionsPreview": True},
    }
    if scenarios:
        payload["whatIfAnalysis"] = {
            "objective": "MAXIMIZE_TARGET",
            "scenarios": [{
                "code": "DURATION_UP_5",
                "changes": [{"column": "duration_seconds", "percentChange": 5}],
            }, {
                "code": "DURATION_DOWN_5",
                "changes": [{"column": "duration_seconds", "percentChange": -5}],
            }],
        }
    return ExecutionCommand.model_validate({
        "schemaVersion": "1.0", "eventId": str(uuid4()),
        "correlationId": "ml-summary-test", "executionId": str(uuid4()),
        "entityId": str(entity_id), "actorUserId": str(uuid4()),
        "occurredAt": datetime.now(timezone.utc).isoformat(),
        "executionType": "ML", "authorization": {"roles": ["SCIENTIST"]},
        "configuration": {"llm": {
            "provider": "MOCK", "baseUrl": "http://unused", "model": "mock",
            "timeoutSeconds": 10, "maxRetries": 0, "maxContextMessages": 10,
            "maxContextCharacters": 1000,
        }},
        "order": {
            "schemaVersion": "1.0", "executionType": "ML",
            "entityId": str(entity_id), "requestedLanguage": language,
            "requestSummary": "Identify calls likely to last longer than five minutes.",
            "constraints": {"maxPreviewRows": 100, "timeoutSeconds": 7200},
            "payload": payload,
        },
    })


def report_result() -> dict:
    return {
        "rowCount": 5,
        "preview": {
            "columns": [{"name": "customer_id", "type": "STRING"}],
            "rows": [{"customer_id": "SECRET-CUSTOMER-42", "charge": 999}],
            "limit": 100, "truncated": False,
        },
        "kpis": [{"code": "INTERNAL", "value": 999,
                  "customerId": "SECRET-CUSTOMER-42"}],
        "charts": [{
            "chartId": "chart-1", "type": "BAR", "categoryField": "region",
            "valueField": "total_charge", "categories": ["Karadeniz", "Ege"],
            "series": [{"name": "Total charge", "data": [1476422.30, 1471585.63]}],
        }],
        "summaryFacts": {
            "schemaVersion": "2.0",
            "reportBreakdown": [
                {"region": "Karadeniz", "customer_id": "SECRET-1",
                 "call_count": 200000, "total_charge": 1476422.30},
                {"region": "Ege", "customer_id": "SECRET-2",
                 "call_count": 200000, "total_charge": 1471585.63},
            ],
            "reportComparisons": [{
                "measure": "total_charge",
                "highest": {
                    "dimensions": {"region": "Karadeniz", "customer_id": "SECRET-1"},
                    "value": 1476422.30,
                },
                "lowest": {"dimensions": {"region": "Ege"}, "value": 1471585.63},
                "absoluteSpread": 4836.67,
                "relativeSpread": {
                    "method": "SYMMETRIC_PERCENT_DIFFERENCE", "percent": 0.3288,
                    "meaning": "RELATIVE_SPREAD_BETWEEN_HIGHEST_AND_LOWEST",
                },
                "highestShareOfTotalPercent": 20.04,
                "groupCount": 5,
            }],
            "normalizedComparisons": [{
                "numeratorMeasure": "total_charge", "denominatorMeasure": "call_count",
                "highest": {"dimensions": {"region": "Karadeniz"}, "value": 7.3821},
                "lowest": {"dimensions": {"region": "Ege"}, "value": 7.3579},
                "absoluteSpread": 0.0242,
                "relativeSpread": {
                    "method": "SYMMETRIC_PERCENT_DIFFERENCE", "percent": 0.3283,
                    "meaning": "RELATIVE_SPREAD_BETWEEN_HIGHEST_AND_LOWEST",
                },
            }],
        },
        "warnings": [{"code": "RESULT_TRUNCATED",
                      "messageKey": "result.warning.truncated", "raw": "SECRET-ROW"}],
    }


def neutral_report_command(language: str = "en") -> ExecutionCommand:
    value = report_command(language).model_dump(by_alias=True, mode="json")
    value["order"]["requestSummary"] = "Compare governed measures by an arbitrary dimension."
    value["order"]["payload"].update({
        "select": [{"column": "group_alpha", "displayLabel": "Group alpha"}],
        "groupBy": ["group_alpha"],
        "aggregations": [
            {
                "function": "COUNT", "column": None, "alias": "record_count",
                "displayLabel": "Record count",
            },
            {
                "function": "SUM", "column": "measure_beta",
                "alias": "measured_amount", "displayLabel": "Measured amount",
            },
        ],
        "orderBy": [{"column": "measured_amount", "direction": "DESC"}],
    })
    return ExecutionCommand.model_validate(value)


def neutral_report_result() -> dict:
    return {
        "rowCount": 2,
        "preview": {"rows": [{"private_identifier": "NEVER-SEND"}]},
        "kpis": [],
        "charts": [],
        "summaryFacts": {
            "schemaVersion": "2.0",
            "reportComparisons": [{
                "measure": "measured_amount",
                "highest": {"dimensions": {"group_alpha": "Group A"}, "value": 120.0},
                "lowest": {"dimensions": {"group_alpha": "Group B"}, "value": 80.0},
                "absoluteSpread": 40.0,
                "relativeSpread": {
                    "method": "SYMMETRIC_PERCENT_DIFFERENCE", "percent": 40.0,
                    "meaning": "RELATIVE_SPREAD_BETWEEN_HIGHEST_AND_LOWEST",
                },
                "highestShareOfTotalPercent": 60.0,
                "groupCount": 2,
            }],
            "normalizedComparisons": [{
                "numeratorMeasure": "measured_amount",
                "denominatorMeasure": "record_count",
                "highest": {"dimensions": {"group_alpha": "Group A"}, "value": 12.0},
                "lowest": {"dimensions": {"group_alpha": "Group B"}, "value": 8.0},
                "absoluteSpread": 4.0,
                "relativeSpread": {
                    "method": "SYMMETRIC_PERCENT_DIFFERENCE", "percent": 40.0,
                    "meaning": "RELATIVE_SPREAD_BETWEEN_HIGHEST_AND_LOWEST",
                },
            }],
            "timeChanges": [{
                "measure": "measured_amount",
                "earlier": {"dimensions": {"period": "2030-01"}, "value": 100.0},
                "later": {"dimensions": {"period": "2030-02"}, "value": 110.0},
                "absoluteChange": 10.0,
                "percentageChange": 10.0,
            }],
        },
        "warnings": [],
    }


def ml_result(scenarios: bool = False) -> dict:
    charts = [{
        "chartId": "feature-importance", "type": "BAR",
        "categories": [
            "call_type: SMS", "call_type: VOICE", "origin_region: Marmara",
            "customer_id: secret",
        ],
        "series": [{"name": "importance", "data": [0.42, 0.18, 0.25, 0.99]}],
    }]
    warnings = []
    if scenarios:
        charts.append({
            "chartId": "what-if-analysis", "type": "BAR",
            "objective": "MAXIMIZE_TARGET",
            "scenarioFacts": [{
                "code": "DURATION_UP_5",
                "changes": [{"column": "duration_seconds", "percentChange": 5}],
                "baselinePrediction": 0.40, "scenarioPrediction": 0.44,
                "delta": 0.04, "deltaPercent": 10,
            }, {
                "code": "DURATION_DOWN_5",
                "changes": [{"column": "duration_seconds", "percentChange": -5}],
                "baselinePrediction": 0.40, "scenarioPrediction": 0.36,
                "delta": -0.04, "deltaPercent": -10,
            }],
        })
        warnings.append({"code": "WHAT_IF_NOT_CAUSAL",
                         "messageKey": "result.warning.whatIfNotCausal"})
    return {
        "rowCount": 1500,
        "preview": {"rows": [{"subscriber_id": "SECRET-99", "prediction": 1}]},
        "kpis": [
            {"code": "ACCURACY", "value": 0.89},
            {"code": "AUC", "value": 0.91},
            {"code": "F1", "value": 0.84},
            {"code": "POSITIVE_PRECISION", "value": 78.0, "unit": "PERCENT"},
            {"code": "POSITIVE_RECALL", "value": 64.0, "unit": "PERCENT"},
            {"code": "BASELINE_ACCURACY", "value": 70.0, "unit": "PERCENT"},
            {"code": "TEST_CASE_COUNT", "value": 1500, "unit": "COUNT"},
            {"code": "SELECTED_ALGORITHM", "value": "DECISION_TREE_CLASSIFIER"},
            {"code": "BEST_VALIDATION_SCORE", "value": 0.90, "unit": "AUC"},
            {"code": "TUNING_TRIALS_EVALUATED", "value": 6},
            {"code": "CANDIDATE_ALGORITHMS_EVALUATED", "value": 2},
        ],
        "charts": charts,
        "warnings": warnings,
    }


class SequenceProvider:
    name = "recording"
    model = "recording"

    def __init__(self, *responses: str, fail: bool = False):
        self.responses = list(responses)
        self.fail = fail
        self.calls = 0
        self.messages = []

    async def stream(self, messages):
        self.messages.append(messages)
        if self.fail:
            raise ProviderError("LLM_PROVIDER_UNAVAILABLE")
        response = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        yield response


class Registry:
    def __init__(self, provider):
        self.provider = provider

    def resolve(self, config):
        return self.provider


class StructuredSequenceProvider(SequenceProvider):
    async def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        self.messages.append((system_prompt, user_prompt))
        response = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return json.loads(response)

    async def stream(self, messages):
        raise AssertionError("structured management summaries must not use chat streaming")


class PlainRecoveryProvider(SequenceProvider):
    def __init__(self, rejected: str, recovered_prose: str):
        super().__init__(rejected)
        self.recovered_prose = recovered_prose

    async def stream(self, messages):
        self.messages.append(messages)
        self.calls += 1
        if "service owns all claim metadata" in messages[0]["content"]:
            yield json.dumps({"prose": self.recovered_prose})
        else:
            yield self.responses[0]


def codes(validation) -> set[str]:
    return {item.code for item in validation.violations}


def test_report_evidence_is_typed_complete_and_privacy_safe():
    evidence = ManagementEvidenceBuilder().build(report_command(), report_result())

    assert evidence.schema_version == "2.0"
    assert evidence.policy.contains_raw_rows is False
    assert evidence.policy.recommendation_authority == RecommendationAuthority.NONE
    assert evidence.report_comparisons[0].scope == "COMPLETE_RESULT"
    assert evidence.report_comparisons[0].population_scope == "GROUPED"
    assert evidence.report_comparisons[0].grouping_dimensions == ["region"]
    assert evidence.report_comparisons[0].relative_spread.meaning == (
        "RELATIVE_SPREAD_BETWEEN_HIGHEST_AND_LOWEST"
    )
    assert evidence.normalized_comparisons[0].meaning == "NUMERATOR_PER_DENOMINATOR"
    assert evidence.report_highlights[0].scope == "BOUNDED_CHART_DATA"
    serialized = evidence.model_dump_json(by_alias=True)
    assert "SECRET-CUSTOMER-42" not in serialized
    assert "SECRET-1" not in serialized
    assert "SECRET-ROW" not in serialized
    assert '"preview"' not in serialized
    assert '"customer_id"' not in serialized


def test_management_evidence_json_schema_is_explicitly_versioned():
    schema = ManagementEvidence.model_json_schema(by_alias=True)

    assert schema["properties"]["schemaVersion"]["const"] == "2.0"
    assert schema["properties"]["semanticRegistryVersion"]["const"] == "1.0"
    assert schema["properties"]["policy"]
    assert schema["properties"]["reportComparisons"]
    assert schema["properties"]["metrics"]


def test_semantic_registry_covers_every_required_generic_meaning():
    required = {
        SemanticKey.SUM, SemanticKey.COUNT, SemanticKey.COUNT_DISTINCT,
        SemanticKey.AVG, SemanticKey.MIN, SemanticKey.MAX,
        SemanticKey.ABSOLUTE_DIFFERENCE, SemanticKey.SYMMETRIC_RELATIVE_SPREAD,
        SemanticKey.SHARE_OF_TOTAL, SemanticKey.TIME_PERCENTAGE_CHANGE,
        SemanticKey.NORMALIZED_PER_DENOMINATOR, SemanticKey.MAE, SemanticKey.RMSE,
        SemanticKey.R2, SemanticKey.ACCURACY, SemanticKey.PRECISION,
        SemanticKey.RECALL, SemanticKey.SPECIFICITY, SemanticKey.F1,
        SemanticKey.AUC, SemanticKey.BASELINE_ACCURACY, SemanticKey.SAMPLE_COUNT,
        SemanticKey.VALIDATION_SCORE, SemanticKey.TEST_SCORE,
        SemanticKey.FEATURE_IMPORTANCE, SemanticKey.SCENARIO_DELTA,
    }

    assert required.issubset(SEMANTIC_REGISTRY)
    assert all(item.permitted_interpretations for item in SEMANTIC_REGISTRY.values())
    assert all(item.forbidden_interpretations for item in SEMANTIC_REGISTRY.values())

    report_evidence = ManagementEvidenceBuilder().build(report_command(), report_result())
    highlight = report_evidence.report_highlights[0]
    assert highlight.scope in SEMANTIC_REGISTRY[
        highlight.measure.semantic_key
    ].valid_scopes


def test_arbitrary_future_entity_uses_generic_evidence_without_raw_records():
    evidence = ManagementEvidenceBuilder().build(
        neutral_report_command(), neutral_report_result(),
    )
    serialized = evidence.model_dump_json(by_alias=True)

    assert evidence.report_comparisons[0].measure.label == "Measured amount"
    assert evidence.report_comparisons[0].measure.semantic_key == SemanticKey.SUM
    assert evidence.normalized_comparisons[0].semantic_key == (
        SemanticKey.NORMALIZED_PER_DENOMINATOR
    )
    assert evidence.time_changes[0].semantic_key == SemanticKey.TIME_PERCENTAGE_CHANGE
    assert "NEVER-SEND" not in serialized
    assert "private_identifier" not in serialized


def test_relative_spread_share_and_time_change_remain_distinct_typed_meanings():
    evidence = ManagementEvidenceBuilder().build(
        neutral_report_command(), neutral_report_result(),
    )
    comparison = evidence.report_comparisons[0]
    change = evidence.time_changes[0]

    assert comparison.relative_spread.percent == 40
    assert comparison.highest_share_of_total_percent == 60
    assert change.percentage_change == 10
    assert change.method == "LATER_MINUS_EARLIER_OVER_ABSOLUTE_EARLIER"


def test_claim_scope_carries_exact_groups_periods_aggregations_and_selection_context():
    report_evidence = ManagementEvidenceBuilder().build(
        neutral_report_command(), neutral_report_result(),
    )
    report_facts = evidence_index(report_evidence)
    comparison_scope = expected_scope([
        report_facts["report.comparison.measured_amount"],
    ])
    time_scope = expected_scope([
        report_facts["report.time-change.measured_amount.1"],
    ])
    ml_evidence = ManagementEvidenceBuilder().build(ml_command(), ml_result())
    selection_scope = expected_scope([evidence_index(ml_evidence)["ml.model-selection"]])

    assert comparison_scope.grouping_dimensions == ["group_alpha"]
    assert comparison_scope.grouping_values == [
        {"group_alpha": "Group A"}, {"group_alpha": "Group B"},
    ]
    assert comparison_scope.aggregations == ["SUM"]
    assert time_scope.periods == ["2030-01", "2030-02"]
    assert selection_scope.dataset_roles == ["VALIDATION_DATA"]
    assert selection_scope.selected_models == ["DECISION_TREE_CLASSIFIER"]
    assert selection_scope.selection_metrics == ["AUC"]


def test_legacy_untyped_report_facts_are_not_silently_reinterpreted():
    value = report_result()
    value["summaryFacts"] = {
        "reportComparisons": [{
            "measure": "total_charge", "highestDimensions": {"region": "Karadeniz"},
            "highestValue": 10, "lowestDimensions": {"region": "Ege"},
            "lowestValue": 1, "absoluteDifference": 9, "percentageDifference": 100,
            "groupCount": 2,
        }],
    }

    evidence = ManagementEvidenceBuilder().build(report_command(), value)

    assert evidence.report_comparisons == []


def test_scalar_aggregate_is_first_class_complete_result_evidence():
    value = report_result()
    value["rowCount"] = 1
    value["charts"] = []
    value["summaryFacts"] = {
        "schemaVersion": "2.0",
        "reportMeasures": [{"measure": "total_charge", "value": 7248007.93}],
        "reportComparisons": [], "normalizedComparisons": [],
    }

    evidence = ManagementEvidenceBuilder().build(report_command(scalar=True), value)

    assert len(evidence.report_measure_results) == 1
    assert evidence.report_measure_results[0].measure.label == "Total charge"
    assert evidence.report_measure_results[0].value == 7248007.93
    assert evidence.report_measure_results[0].scope == "COMPLETE_RESULT"


def test_ml_evidence_preserves_metric_semantics_and_selection_scope():
    evidence = ManagementEvidenceBuilder().build(ml_command(), ml_result())
    metrics = {item.code: item for item in evidence.metrics}

    assert metrics["ACCURACY"].value == 89
    assert metrics["AUC"].value == 91
    assert "rank positive cases" in metrics["AUC"].business_definition
    assert metrics["POSITIVE_PRECISION"].value == 78
    assert metrics["POSITIVE_RECALL"].value == 64
    assert evidence.model_selection.selected_algorithm == "DECISION_TREE_CLASSIFIER"
    assert evidence.model_selection.candidate_algorithms_evaluated == 2
    assert evidence.model_selection.tuning_trials_evaluated == 6
    assert evidence.model_selection.selection_basis == "VALIDATION_DATA_ONLY"
    assert evidence.model_selection.final_metrics_scope == "UNTOUCHED_TEST_DATA"
    assert evidence.feature_columns == [
        "call_type", "origin_region", "duration_seconds",
    ]


def test_ml_summary_request_contains_complete_calculated_outcome_without_preview_rows():
    command = ml_command()
    result = ml_result()
    result["preview"] = {
        "columns": [{"name": "subscriber_id", "type": "STRING"}],
        "rows": [["SECRET-SUBSCRIBER"]],
    }
    provider = SequenceProvider(json.dumps({"prose": (
        "The calculated classifications can support human review. The calculation relied "
        "most on call_type and origin_region."
    )}))

    asyncio.run(ResultExplainer(Registry(provider)).explain(command, result))

    request = json.dumps(provider.messages[0], ensure_ascii=False)
    assert "featureColumns" in request
    assert "metrics" in request
    assert "modelSelection" in request
    assert "drivers" in request
    assert "DECISION_TREE_CLASSIFIER" in request
    assert "SECRET-SUBSCRIBER" not in request
    assert "Do not mention algorithms, models, metrics, scores" not in request


def test_encoded_driver_categories_are_aggregated_without_direction_or_identifiers():
    evidence = ManagementEvidenceBuilder().build(ml_command(), ml_result())

    assert [(item.feature, item.importance) for item in evidence.drivers] == [
        ("call_type", pytest.approx(0.60)),
        ("origin_region", pytest.approx(0.25)),
    ]
    assert all(item.direction_known is False and item.causal is False
               for item in evidence.drivers)


def test_identifier_targets_and_scenario_fields_do_not_cross_the_summary_boundary():
    command = ml_command(scenarios=True).model_copy(deep=True)
    command.order.payload.target_column = "customer_id"
    result = ml_result(scenarios=True)
    result["charts"][-1]["scenarioFacts"][0]["changes"] = [
        {"column": "customer_id", "percentChange": 5},
    ]

    evidence = ManagementEvidenceBuilder().build(command, result)
    serialized = evidence.model_dump_json(by_alias=True)

    assert evidence.target is None
    assert all(item.code != "DURATION_UP_5" for item in evidence.scenarios)
    assert "customer_id" not in serialized


def test_scenario_evidence_is_the_only_recommendation_authority():
    without = ManagementEvidenceBuilder().build(ml_command(), ml_result())
    with_scenarios = ManagementEvidenceBuilder().build(
        ml_command(scenarios=True), ml_result(scenarios=True),
    )

    assert without.policy.recommendation_authority == RecommendationAuthority.NONE
    assert with_scenarios.policy.recommendation_authority == (
        RecommendationAuthority.CONDITIONAL_SCENARIO_ONLY
    )
    assert with_scenarios.policy.authorized_scenario_code == "DURATION_UP_5"
    assert with_scenarios.scenarios[0].causal is False
    assert with_scenarios.scenarios[0].delta_percent == 10


def test_recommendation_must_follow_the_authorized_scenario_direction():
    evidence = ManagementEvidenceBuilder().build(
        ml_command(scenarios=True), ml_result(scenarios=True),
    )
    wrong = ManagementSummaryValidator().validate(
        "Management should decrease duration by 5% in a limited pilot because the tested "
        "scenario differed by 10% from the 0.40 baseline.",
        evidence,
    )
    supported = ManagementSummaryValidator().validate(
        "Under the calculated scenarios, management should increase duration by 5% only in "
        "a limited pilot; that scenario differed by 10% from the 0.40 baseline.",
        evidence,
    )

    assert "RECOMMENDATION_DIRECTION_MISMATCH" in codes(wrong)
    assert "RECOMMENDATION_DIRECTION_MISMATCH" not in codes(supported)


def test_validator_rejects_report_directionality_percentage_meaning_and_currency():
    validator = ManagementSummaryValidator()
    evidence = ManagementEvidenceBuilder().build(report_command(), report_result())

    validation = validator.validate(
        "Karadeniz was the best performer and its 0.33% was a share of the total in euros.",
        evidence,
    )

    assert validation.status == "REJECTED"
    assert {
        "UNSUPPORTED_REPORT_DIRECTIONALITY", "RELATIVE_SPREAD_MISSTATED",
        "UNAPPROVED_CURRENCY",
    }.issubset(codes(validation))


def test_validator_rejects_invented_physical_unit_without_metadata():
    evidence = ManagementEvidenceBuilder().build(report_command(), report_result())

    validation = ManagementSummaryValidator().validate(
        "Karadeniz recorded the highest Total charge at 1,476,422.30 seconds, while "
        "Ege recorded the lowest at 1,471,585.63.",
        evidence,
    )

    assert "UNAPPROVED_UNIT" in codes(validation)


def test_validator_accepts_exact_report_semantics_without_calling_highest_better():
    evidence = ManagementEvidenceBuilder().build(report_command(), report_result())
    summary = (
        "Karadeniz recorded the highest total charge at 1,476,422.30, while Ege recorded "
        "the lowest at 1,471,585.63. The absolute spread was 4,836.67, and the relative "
        "spread between those values was 0.33%. Charge per call was also slightly higher "
        "in Karadeniz at 7.3821 than in Ege at 7.3579."
    )

    assert ManagementSummaryValidator().validate(summary, evidence).status == "ACCEPTED"


def test_request_repetition_and_execution_mechanics_are_advisory():
    evidence = ManagementEvidenceBuilder().build(report_command(), report_result())
    validation = ManagementSummaryValidator().validate(
        "Compare call count and total charge by region. Spark then created a DataFrame for "
        "the result, where Karadeniz recorded Total charge of 1,476,422.30.",
        evidence,
    )

    assert {"REQUEST_REPETITION", "EXECUTION_MECHANICS_EXPOSED"}.issubset(
        codes(validation)
    )


def test_validator_rejects_invented_numbers_and_causality():
    evidence = ManagementEvidenceBuilder().build(report_command(), report_result())
    validation = ManagementSummaryValidator().validate(
        "Karadeniz recorded 9,999,999 because its region caused higher total charge, while "
        "Ege recorded the lowest value.",
        evidence,
    )

    assert {"UNAPPROVED_NUMBER", "UNSUPPORTED_CAUSALITY"}.issubset(codes(validation))


def test_validator_rejects_metric_probability_and_error_percent_meanings():
    regression = ml_result()
    regression["kpis"] = [
        {"code": "R2", "value": 0.9939},
        {"code": "RMSE", "value": 6.10},
    ]
    command = ml_command().model_copy(deep=True)
    command.order.payload.problem_type = "REGRESSION"
    command.order.payload.target_column = "charge"
    command.order.payload.binary_target_derivation = None
    evidence = ManagementEvidenceBuilder().build(command, regression)

    validation = ManagementSummaryValidator().validate(
        "The result has 99.39% confidence and a 6.10% larger-error-sensitive difference.",
        evidence,
    )

    assert {"METRIC_MEANING_MISSTATED", "ERROR_METRIC_UNIT_MISSTATED"}.issubset(
        codes(validation)
    )


def regression_evidence() -> ManagementEvidence:
    value = ml_result()
    value["kpis"] = [
        {"code": "MAE", "value": 0.251},
        {"code": "RMSE", "value": 0.563},
        {"code": "R2", "value": 0.9939},
        {"code": "SELECTED_ALGORITHM", "value": "LINEAR_REGRESSION"},
        {"code": "BEST_VALIDATION_SCORE", "value": 0.58, "unit": "RMSE"},
        {"code": "TUNING_TRIALS_EVALUATED", "value": 4},
        {"code": "CANDIDATE_ALGORITHMS_EVALUATED", "value": 3},
    ]
    command = ml_command().model_copy(deep=True)
    command.order.payload.problem_type = "REGRESSION"
    command.order.payload.target_column = "outcome_value"
    command.order.payload.binary_target_derivation = None
    return ManagementEvidenceBuilder().build(command, value)


@pytest.mark.parametrize(("summary", "expected"), [
    (
        "RMSE of 0.563 is the average error magnitude and the model accuracy is measured "
        "with MAE of 0.251 and R2 of 99.39%.",
        {"RMSE_MEAN_MAGNITUDE_MISSTATED", "METRICS_MISLABELED_AS_ACCURACY"},
    ),
    (
        "R2 of 99.39% means the model is highly reliable with 99.39% confidence.",
        {"METRIC_MEANING_MISSTATED", "QUALITATIVE_PERFORMANCE_UNSUPPORTED"},
    ),
])
def test_regression_metric_adversarial_interpretations_are_rejected(summary, expected):
    validation = ManagementSummaryValidator().validate(summary, regression_evidence())

    assert expected.issubset(codes(validation))


def test_binary_management_summary_does_not_require_a_metric_inventory():
    evidence = ManagementEvidenceBuilder().build(ml_command(), ml_result())
    validation = ManagementSummaryValidator().validate(
        "The calculated classifications can support screening and human review.", evidence,
    )

    assert validation.status == "ACCEPTED"


def test_wrong_localized_language_is_blocking():
    evidence = ManagementEvidenceBuilder().build(report_command("tr"), report_result())
    validation = ManagementSummaryValidator().validate(
        "Karadeniz recorded the highest total charge while Ege recorded the lowest value "
        "in the complete regional comparison.",
        evidence,
    )

    assert "WRONG_LANGUAGE" in codes(validation)


def test_mixed_language_summary_is_blocking_but_governed_labels_are_allowed():
    evidence = ManagementEvidenceBuilder().build(report_command("tr"), report_result())
    mixed = ManagementSummaryValidator().validate(
        "Total charge Karadeniz için 1.476.422,30 olarak hesaplandı. "
        "This separate sentence changes the narrative language without justification.",
        evidence,
    )
    localized = ManagementSummaryValidator().validate(
        "Total charge Karadeniz için 1.476.422,30, Ege için 1.471.585,63 olarak "
        "hesaplandı; iki grup arasındaki mutlak fark 4.836,67 oldu.",
        evidence,
    )

    assert {"WRONG_LANGUAGE", "MIXED_LANGUAGE"}.intersection(codes(mixed))
    assert not {"WRONG_LANGUAGE", "MIXED_LANGUAGE"}.intersection(codes(localized))


def test_zero_result_can_only_describe_no_matching_data():
    value = report_result()
    value.update({"rowCount": 0, "charts": [], "summaryFacts": {"schemaVersion": "2.0"}})
    evidence = ManagementEvidenceBuilder().build(report_command(), value)

    rejected = ManagementSummaryValidator().validate(
        "The report shows useful regional comparisons for management.", evidence,
    )
    accepted = ManagementSummaryValidator().validate(
        "No matching data was found for the requested report scope.", evidence,
    )

    assert "ZERO_RESULT_HALLUCINATION" in codes(rejected)
    assert accepted.status == "ACCEPTED"


def test_explainer_repairs_blocking_output_and_persists_llm_generated_text():
    command = report_command()
    provider = SequenceProvider(
        json.dumps({"prose": (
            "Karadeniz was the best group for Total charge at 1,476,422.30 euros."
        )}),
        json.dumps({"prose": (
            "Karadeniz recorded the highest grouped Total charge at 1,476,422.30, while "
            "Ege recorded the lowest at 1,471,585.63; the absolute difference was 4,836.67. "
            "This comparison can support review of where the calculated values differ."
        )}),
    )

    outcome = asyncio.run(ResultExplainer(Registry(provider)).explain(
        command, report_result(),
    ))

    assert provider.calls == 2
    assert outcome.status == "COMPLETED"
    assert outcome.validation_status == "ACCEPTED_WITH_ADVISORIES"
    assert outcome.text.startswith("Karadeniz recorded")
    assert outcome.evidence.schema_version == "2.0"
    assert outcome.summary_audit is not None
    assert outcome.repair_attempt_count == 1
    repair_payload = json.dumps(provider.messages[1], ensure_ascii=False)
    assert "UNAPPROVED_CURRENCY" in repair_payload
    assert "calculatedResult" in repair_payload
    assert "SECRET-CUSTOMER-42" not in repair_payload


def test_explicit_denial_of_causality_is_not_rejected_as_a_causal_claim():
    evidence = regression_evidence()

    validation = ManagementSummaryValidator().validate(
        "The estimates do not prove that the available fields caused particular outcomes. "
        "They can be used as a second reference during human review.",
        evidence,
    )

    assert "UNSUPPORTED_CAUSALITY" not in codes(validation)


def test_plain_prose_repair_corrects_semantic_misstatement():
    command = report_command()
    provider = SequenceProvider(
        json.dumps({"prose": (
            "Total charge had relative spread of 0.33%, representing growth between groups."
        )}),
        json.dumps({"prose": (
            "Total charge ranged from 1,471,585.63 for Ege to 1,476,422.30 for Karadeniz, "
            "with a relative spread of 0.33% between the grouped values. This comparison "
            "can support review of differences across the grouped result."
        )}),
    )

    outcome = asyncio.run(ResultExplainer(Registry(provider)).explain(
        command, report_result(),
    ))

    assert outcome.status == "COMPLETED"
    assert provider.calls == 2
    assert outcome.summary_audit is not None
    assert outcome.summary_audit.schema_version == "2.0"
    assert outcome.summary_audit.prose == outcome.text
    assert "growth" not in outcome.text


def test_combined_report_prose_does_not_cross_match_independent_fact_semantics():
    command = neutral_report_command()
    provider = SequenceProvider(json.dumps({"prose": (
        "Measured amount ranged from 80 for Group B to 120 for Group A, with a relative "
        "spread of 40% between those grouped values. Between January and February 2030, "
        "Measured amount changed from 100 to 110, a 10% increase. These comparisons can "
        "support monitoring and planning within the requested scope."
    )}))

    outcome = asyncio.run(ResultExplainer(Registry(provider)).explain(
        command, neutral_report_result(),
    ))

    assert outcome.status == "COMPLETED"
    assert outcome.validation_status in {"ACCEPTED", "ACCEPTED_WITH_ADVISORIES"}
    assert provider.calls == 1


def test_malformed_plain_response_is_retried_once():
    command = report_command()
    provider = SequenceProvider(
        json.dumps({"notTheRequiredDraft": True}),
        json.dumps({"prose": (
            "Total charge ranged from 1,471,585.63 for Ege to 1,476,422.30 for Karadeniz. "
            "This comparison can support review across the grouped result."
        )}),
    )

    outcome = asyncio.run(ResultExplainer(Registry(provider)).explain(
        command, report_result(),
    ))

    assert outcome.status == "COMPLETED"
    assert provider.calls == 2
    assert outcome.summary_audit is not None
    assert "growth" not in outcome.text


def test_service_owned_metadata_has_no_provider_claim_components():
    command = report_command()
    provider = SequenceProvider(json.dumps({"prose": (
        "Total charge ranged from 1,471,585.63 for Ege to 1,476,422.30 for Karadeniz. "
        "This comparison can support review across the grouped result."
    )}))

    outcome = asyncio.run(ResultExplainer(Registry(provider)).explain(
        command, report_result(),
    ))

    assert outcome.status == "COMPLETED"
    assert outcome.validation_status == "ACCEPTED"
    assert outcome.summary_audit is not None
    assert outcome.summary_audit.prose == outcome.text
    assert outcome.summary_audit.evidence_ids
    serialized = outcome.summary_audit.model_dump(by_alias=True, mode="json")
    assert set(serialized) == {"schemaVersion", "language", "prose", "evidenceIds", "scope"}


def test_unrepairable_blocking_output_is_not_published_as_management_text():
    command = report_command()
    provider = SequenceProvider(
        json.dumps({"prose": (
            "Karadeniz is the best group for Total charge and management should increase it."
        )})
    )

    outcome = asyncio.run(ResultExplainer(Registry(provider)).explain(
        command, report_result(),
    ))

    assert provider.calls == 2
    assert outcome.status == "FAILED"
    assert outcome.text is None
    assert outcome.validation_status == "REJECTED"


def test_classification_management_summary_keeps_measurements_in_technical_cards():
    command = ml_command()
    provider = SequenceProvider(json.dumps({"prose": (
        "The calculated classifications can be used to prioritize cases for human review and "
        "support screening without automatically deciding the business outcome."
    )}))

    outcome = asyncio.run(ResultExplainer(Registry(provider)).explain(
        command, ml_result(),
    ))

    assert provider.calls == 1
    assert outcome.status == "COMPLETED"
    assert outcome.validation_status == "ACCEPTED"
    assert "89" not in outcome.text


def test_provider_failure_does_not_fail_the_completed_analytical_result():
    provider = SequenceProvider("unused", fail=True)

    outcome = asyncio.run(ResultExplainer(Registry(provider)).explain(
        report_command(), report_result(),
    ))

    assert outcome.status == "FAILED"
    assert outcome.text is None
    assert outcome.validation_status == "PROVIDER_FAILED"
    assert outcome.validation_issues == ["SUMMARY_PROVIDER_FAILED"]
    assert outcome.blocking_issues == ["SUMMARY_PROVIDER_FAILED"]
    assert outcome.evidence.report_comparisons
    assert outcome.provider == "recording"
    assert outcome.provider_model == "recording"
    assert outcome.generated_at.tzinfo is not None


def test_management_summary_has_no_length_rejection():
    value = report_result()
    value["rowCount"] = 1
    value["charts"] = []
    value["summaryFacts"] = {
        "schemaVersion": "2.0",
        "reportMeasures": [{"measure": "total_charge", "value": 7248007.93}],
    }
    evidence = ManagementEvidenceBuilder().build(report_command(scalar=True), value)
    summary = " ".join([
        "The complete result records total charge at 7,248,007.93."
    ] + ["This calculated value describes only the requested scope."] * 1000)

    assert ManagementSummaryValidator().validate(summary, evidence).status == "ACCEPTED"


def test_signed_report_change_can_be_expressed_as_a_positive_decline_magnitude():
    value = report_result()
    value["summaryFacts"] = {
        "schemaVersion": "2.0",
        "timeChanges": [{
            "measure": "total_charge",
            "earlier": {
                "dimensions": {"call_month": "2026-01"},
                "value": 1163202.95,
            },
            "later": {
                "dimensions": {"call_month": "2026-06"},
                "value": 1121446.43,
            },
            "absoluteChange": -41756.52,
            "percentageChange": -3.589788007329247,
        }],
    }
    evidence = ManagementEvidenceBuilder().build(report_command(), value)

    validation = ManagementSummaryValidator().validate(
        "Total Charge Amount declined by 3.59% from January to June, a reduction "
        "of 41,756.52.",
        evidence,
    )

    assert "UNAPPROVED_NUMBER" not in codes(validation)


def test_signed_ml_scenario_delta_can_be_expressed_as_a_positive_decrease_magnitude():
    value = ml_result(scenarios=True)
    decreasing = value["charts"][-1]["scenarioFacts"][1]
    decreasing["deltaPercent"] = -4.7
    decreasing["delta"] = -125.5
    evidence = ManagementEvidenceBuilder().build(ml_command(scenarios=True), value)

    validation = ManagementSummaryValidator().validate(
        "The tested scenario decreased the calculated outcome by 4.7%, a reduction "
        "of 125.5.",
        evidence,
    )

    assert "UNAPPROVED_NUMBER" not in codes(validation)


def test_typed_ml_evidence_uses_localized_business_labels():
    ml_evidence = ManagementEvidenceBuilder().build(ml_command("tr"), ml_result())
    labels = {item.code: item.label for item in ml_evidence.metrics}
    assert labels["AUC"] == "Sıralama ayırt ediciliği"
    assert labels["POSITIVE_RECALL"] == "Olumlu durumların kapsanması"
