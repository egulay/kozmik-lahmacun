import asyncio
import json
import math
from uuid import uuid4

import pytest
from pyspark.sql import SparkSession

import kozmik_executor.execution.spark_ml as spark_ml_module
from kozmik_executor.execution.spark_ml import SparkMlExecutor
from kozmik_executor.planning.api import (
    _enforce_execution_constraints,
    _fit_trial_budget,
    _normalize_ml_features,
    _remove_implicit_what_if_baseline,
    _remove_unrequested_what_if,
    _requires_what_if,
)
from kozmik_executor.planning.ml import validate_ml_order
from kozmik_executor.planning.ml import ALGORITHM_REGISTRY
from kozmik_executor.planning.models import (
    AuthorizedColumn,
    MlOrder,
    ReportPlanningRequest,
)
from kozmik_executor.planning.validation import PlanningValidationError


def request(capabilities=None):
    entity_id = uuid4()
    return ReportPlanningRequest.model_validate({
        "schemaVersion": "1.0", "requestId": str(uuid4()), "correlationId": "ml-test",
        "actorUserId": str(uuid4()), "capabilities": capabilities or ["SCIENTIST"],
        "userRequest": "Predict revenue", "requestedLanguage": "en",
        "authorizedSchema": {
            "entityId": str(entity_id),
            "columns": [
                {"columnName": "units", "businessName": "Units", "dataType": "DECIMAL",


},
                {"columnName": "price", "businessName": "Price", "dataType": "DECIMAL",


},
                {"columnName": "revenue", "businessName": "Revenue", "dataType": "DECIMAL",


},
            ],
        },
    })


def order(value, parameters=None):
    return MlOrder.model_validate({
        "schemaVersion": "1.0", "executionType": "ML",
        "entityId": str(value.authorized_schema.entity_id),

        "requestedLanguage": "en", "requestSummary": "Revenue regression",
        "constraints": {"maxPreviewRows": 5, "timeoutSeconds": 60},
        "payload": {
            "problemType": "REGRESSION", "algorithm": "LINEAR_REGRESSION",
            "targetColumn": "revenue", "featureColumns": ["units", "price"],
            "filters": [], "split": {"strategy": "RANDOM", "trainingRatio": 0.8, "seed": 42},
            "parameters": parameters or {"maxIter": 30, "regParam": 0.0},
            "metrics": ["RMSE", "R2"],
            "output": {"includeFeatureImportance": True,
                       "includePredictionsPreview": True},
        },
    })


def test_ml_validation_enforces_role_and_parameter_ranges():
    reporter = request(["REPORTER"])
    with pytest.raises(PlanningValidationError) as error:
        validate_ml_order(order(reporter), reporter)
    assert "ROLE_NOT_AUTHORIZED" in {issue.code for issue in error.value.issues}
    scientist = request()
    with pytest.raises(PlanningValidationError) as error:
        validate_ml_order(order(scientist, {"maxIter": 5000}), scientist)
    assert "PARAMETER_NOT_ALLOWED" in {issue.code for issue in error.value.issues}


def test_control_plane_overrides_llm_operational_constraints():
    raw = {"constraints": {"maxPreviewRows": 1, "timeoutSeconds": 60}}

    _enforce_execution_constraints(raw, max_preview_rows=100, timeout_seconds=1800)

    assert raw["constraints"] == {
        "maxPreviewRows": 100,
        "timeoutSeconds": 1800,
    }


def test_binary_threshold_target_is_governed_and_prevents_leakage():
    planning = request()
    value = order(planning).model_dump(by_alias=True, mode="json")
    value["payload"].update({
        "problemType": "BINARY_CLASSIFICATION",
        "algorithm": "LOGISTIC_REGRESSION",
        "targetColumn": "high_revenue",
        "binaryTargetDerivation": {
            "sourceColumn": "revenue", "operator": "GT", "threshold": 35,
        },
        "metrics": ["ACCURACY", "F1", "AUC"],
    })
    governed = MlOrder.model_validate(value)

    validate_ml_order(governed, planning)
    governed.payload.feature_columns.append("revenue")
    with pytest.raises(PlanningValidationError) as error:
        validate_ml_order(governed, planning)
    assert "DERIVED_TARGET_SOURCE_IS_FEATURE" in {
        issue.code for issue in error.value.issues
    }


def test_boolean_source_column_is_allowed_only_as_binary_classification_target():
    planning = request()
    planning.authorized_schema.columns.append(AuthorizedColumn.model_validate({
        "columnName": "is_fraud", "businessName": "Confirmed fraud",
        "dataType": "BOOLEAN",
    }))
    value = order(planning).model_dump(by_alias=True, mode="json")
    value["payload"].update({
        "problemType": "BINARY_CLASSIFICATION",
        "algorithm": "LOGISTIC_REGRESSION",
        "targetColumn": "is_fraud",
        "metrics": ["ACCURACY", "F1", "AUC"],
    })
    governed = MlOrder.model_validate(value)

    validate_ml_order(governed, planning)

    governed.payload.problem_type = "REGRESSION"
    governed.payload.algorithm = "LINEAR_REGRESSION"
    governed.payload.metrics = ["RMSE"]
    with pytest.raises(PlanningValidationError) as error:
        validate_ml_order(governed, planning)
    assert "TARGET_NOT_ALLOWED" in {issue.code for issue in error.value.issues}


def test_what_if_validation_allows_only_governed_numeric_features():
    planning = request()
    value = order(planning).model_dump(by_alias=True, mode="json")
    value["payload"]["whatIfAnalysis"] = {
        "objective": "MAXIMIZE_TARGET",
        "scenarios": [{
            "code": "RAISE_UNKNOWN",
            "changes": [{"column": "unknown", "percentChange": 10}],
        }],
    }
    candidate = MlOrder.model_validate(value)

    with pytest.raises(PlanningValidationError) as error:
        validate_ml_order(candidate, planning)

    assert "WHAT_IF_COLUMN_NOT_ALLOWED" in {issue.code for issue in error.value.issues}


@pytest.mark.parametrize("request_text", [
    "Should we increase price or decrease discount?",
    "Tell management whether to adjust quantity.",
    "İndirimi azaltmalı veya fiyatı artırmalı mıyız?",
])
def test_directional_management_requests_require_what_if_analysis(request_text):
    assert _requires_what_if(request_text)


def test_llm_emitted_unchanged_baseline_is_removed_before_order_validation():
    raw = {
        "payload": {
            "whatIfAnalysis": {
                "scenarios": [
                    {"code": "UNCHANGED_BASELINE", "changes": []},
                    {"code": "DISCOUNT_DOWN_5", "changes": [
                        {"column": "discount_rate", "percentChange": -5},
                    ]},
                ],
            },
        },
    }

    _remove_implicit_what_if_baseline(raw)

    assert [item["code"] for item in
            raw["payload"]["whatIfAnalysis"]["scenarios"]] == ["DISCOUNT_DOWN_5"]


def test_unrequested_what_if_analysis_is_removed():
    raw = {
        "payload": {
            "whatIfAnalysis": {
                "objective": "MAXIMIZE_TARGET",
                "scenarios": [{
                    "code": "INVENTED",
                    "changes": [{"column": "price", "percentChange": 5}],
                }],
            },
        },
    }

    _remove_unrequested_what_if(raw, "Predict expected revenue")

    assert "whatIfAnalysis" not in raw["payload"]


def test_ml_features_are_limited_to_supported_authorized_columns():
    planning = request()
    raw = {
        "payload": {
            "targetColumn": "revenue",
            "featureColumns": ["units", "unknown", "revenue", "units", "price"],
        },
    }

    _normalize_ml_features(raw, planning)

    assert raw["payload"]["featureColumns"] == ["units", "price"]


def test_ml_features_exclude_the_derived_target_source():
    planning = request()
    raw = {
        "payload": {
            "targetColumn": "high_revenue",
            "binaryTargetDerivation": {
                "sourceColumn": "revenue", "operator": "GT", "threshold": 35,
            },
            "featureColumns": ["units", "revenue", "price"],
        },
    }

    _normalize_ml_features(raw, planning)

    assert raw["payload"]["featureColumns"] == ["units", "price"]


@pytest.mark.parametrize(
    ("problem_type", "algorithm", "metrics", "parameters"),
    [
        ("REGRESSION", "LINEAR_REGRESSION", ["RMSE"], {"maxIter": 30}),
        ("BINARY_CLASSIFICATION", "LOGISTIC_REGRESSION", ["AUC"], {"maxIter": 30}),
        ("REGRESSION", "DECISION_TREE_REGRESSOR", ["R2"], {"maxDepth": 5}),
        ("BINARY_CLASSIFICATION", "DECISION_TREE_CLASSIFIER", ["F1"], {"maxDepth": 5}),
        ("REGRESSION", "RANDOM_FOREST_REGRESSOR", ["MAE"], {"numTrees": 20}),
        ("BINARY_CLASSIFICATION", "RANDOM_FOREST_CLASSIFIER", ["PRECISION"], {"numTrees": 20}),
        ("REGRESSION", "GBT_REGRESSOR", ["RMSE"], {"maxIter": 20}),
        ("BINARY_CLASSIFICATION", "GBT_CLASSIFIER", ["RECALL"], {"maxIter": 20}),
        ("REGRESSION", "XGBOOST_REGRESSOR", ["R2"], {"numRounds": 20}),
        ("BINARY_CLASSIFICATION", "XGBOOST_CLASSIFIER", ["AUC"], {"numRounds": 20}),
    ],
)
def test_governed_algorithm_registry_accepts_supported_problem_type_pairs(
    problem_type, algorithm, metrics, parameters,
):
    planning = request()
    value = order(planning).model_copy(deep=True)
    value.payload.problem_type = problem_type
    value.payload.algorithm = algorithm
    value.payload.metrics = metrics
    value.payload.parameters = parameters
    validate_ml_order(value, planning)
    assert (problem_type, algorithm) in ALGORITHM_REGISTRY


def test_algorithm_cannot_be_used_for_wrong_problem_type():
    planning = request()
    value = order(planning).model_copy(deep=True)
    value.payload.algorithm = "RANDOM_FOREST_CLASSIFIER"
    with pytest.raises(PlanningValidationError) as error:
        validate_ml_order(value, planning)
    assert "ALGORITHM_NOT_ALLOWED" in {issue.code for issue in error.value.issues}


def tuned_order(planning, maximum_trials=3):
    value = order(planning).model_dump(by_alias=True, mode="json")
    value["payload"]["candidateAlgorithms"] = [
        {
            "algorithm": "LINEAR_REGRESSION",
            "parameterGrid": {"maxIter": [30, 60], "regParam": [0.0]},
        },
        {
            "algorithm": "DECISION_TREE_REGRESSOR",
            "parameterGrid": {"maxDepth": [4]},
        },
    ]
    value["payload"]["selection"] = {
        "strategy": "TRAIN_VALIDATION_SPLIT",
        "primaryMetric": "RMSE",
        "maximumTrials": maximum_trials,
        "trainingRatio": 0.7,
        "validationRatio": 0.15,
        "testRatio": 0.15,
        "seed": 42,
    }
    return MlOrder.model_validate(value)


def test_tuning_validation_enforces_total_trial_budget():
    planning = request()
    validate_ml_order(tuned_order(planning), planning)
    with pytest.raises(PlanningValidationError) as error:
        validate_ml_order(tuned_order(planning, maximum_trials=2), planning)
    assert "TRIAL_BUDGET_EXCEEDED" in {issue.code for issue in error.value.issues}


def test_gbt_tuning_rejects_serializer_unsafe_iteration_count():
    planning = request()
    value = tuned_order(planning)
    value.payload.candidate_algorithms = [
        value.payload.candidate_algorithms[0].model_copy(update={
            "algorithm": "GBT_REGRESSOR",
            "parameter_grid": {"maxIter": [51], "maxDepth": [5]},
        })
    ]
    value.payload.selection.maximum_trials = 1

    with pytest.raises(PlanningValidationError) as error:
        validate_ml_order(value, planning)

    assert "PARAMETER_NOT_ALLOWED" in {issue.code for issue in error.value.issues}


def test_generated_candidate_grid_is_deterministically_trimmed_to_trial_budget():
    planning = request()
    value = tuned_order(planning, maximum_trials=4)
    value.payload.candidate_algorithms[0].parameter_grid = {
        "maxIter": [20, 40, 60],
        "regParam": [0.0, 0.1, 0.2],
    }
    _fit_trial_budget(value)
    validate_ml_order(value, planning)
    total = sum(
        max(1, math.prod(len(items) for items in candidate.parameter_grid.values()))
        for candidate in value.payload.candidate_algorithms
    )
    assert total <= value.payload.selection.maximum_trials


def test_governed_string_features_require_explicit_categorical_encoding():
    planning = request()
    planning.authorized_schema.columns.append(
        planning.authorized_schema.columns[0].model_copy(
            update={
                "column_name": "region",
                "business_name": "Region",
                "data_type": "STRING",
            }
        )
    )
    value = order(planning).model_copy(deep=True)
    value.payload.feature_columns.append("region")
    with pytest.raises(PlanningValidationError) as error:
        validate_ml_order(value, planning)
    assert "CATEGORICAL_FEATURES_MISMATCH" in {
        issue.code for issue in error.value.issues
    }
    value.payload.categorical_feature_columns = ["region"]
    validate_ml_order(value, planning)


@pytest.mark.parametrize(
    "algorithm",
    [
        "LINEAR_REGRESSION",
        "DECISION_TREE_REGRESSOR",
        "RANDOM_FOREST_REGRESSOR",
        "GBT_REGRESSOR",
        "XGBOOST_REGRESSOR",
    ],
)
def test_every_regression_algorithm_maps_to_a_trusted_estimator(algorithm, monkeypatch):
    for name in (
        "LinearRegression", "DecisionTreeRegressor", "RandomForestRegressor", "GBTRegressor",
    ):
        monkeypatch.setattr(
            spark_ml_module, name,
            lambda _name=name, **kwargs: {"estimator": _name, "parameters": kwargs},
        )
    value = order(request()).model_copy(deep=True)
    value.payload.algorithm = algorithm
    estimator = SparkMlExecutor._estimator(value)
    assert estimator is not None


@pytest.mark.parametrize(
    "algorithm",
    [
        "LOGISTIC_REGRESSION",
        "DECISION_TREE_CLASSIFIER",
        "RANDOM_FOREST_CLASSIFIER",
        "GBT_CLASSIFIER",
        "XGBOOST_CLASSIFIER",
    ],
)
def test_every_classification_algorithm_maps_to_a_trusted_estimator(algorithm, monkeypatch):
    for name in (
        "LogisticRegression", "DecisionTreeClassifier", "RandomForestClassifier", "GBTClassifier",
    ):
        monkeypatch.setattr(
            spark_ml_module, name,
            lambda _name=name, **kwargs: {"estimator": _name, "parameters": kwargs},
        )
    value = order(request()).model_copy(deep=True)
    value.payload.problem_type = "BINARY_CLASSIFICATION"
    value.payload.algorithm = algorithm
    estimator = SparkMlExecutor._estimator(value)
    assert estimator is not None


class MemoryMinio:
    def __init__(self):
        self.uploads = []

    def fput_object(self, bucket, key, path):
        self.uploads.append((bucket, key))


@pytest.fixture(scope="module")
def spark():
    session = (SparkSession.builder.master("local[2]").appName("kozmik-ml-test")
               .config("spark.ui.enabled", "false").getOrCreate())
    yield session
    session.stop()


def test_linear_regression_end_to_end_is_deterministic(tmp_path, spark):
    source = tmp_path / "ml-sales.json"
    source.write_text("\n".join(json.dumps({
        "units": float(index), "price": float(2 + index % 3),
        "revenue": float(index * 4 + (2 + index % 3) * 3),
    }) for index in range(1, 61)), encoding="utf-8")
    planning = request()
    store = MemoryMinio()
    result = asyncio.run(SparkMlExecutor(spark, store).execute(
        uuid4(), order(planning),
        {"datasetUri": str(source), "datasetFormat": "json", "timeoutSeconds": 60},
        asyncio.Event()))
    assert result["rowCount"] > 0
    assert {item["code"] for item in result["kpis"]} == {"RMSE", "R2"}
    assert not any(chart["chartId"] == "feature-importance" for chart in result["charts"])
    assert {bucket for bucket, _ in store.uploads} == {"results", "models"}
    assert result["artifact"]["format"] == "PARQUET"
    assert result["modelArtifact"]["format"] == "SPARK_ML_ZIP"


def test_unscaled_linear_coefficients_are_not_published_as_comparable_importance():
    class LinearModel:
        coefficients = [1.0, 100.0]

    assert SparkMlExecutor._importance(["factor_a", "factor_b"], LinearModel()) == []


def test_regression_executes_bounded_what_if_scenarios(tmp_path, spark):
    source = tmp_path / "ml-what-if.json"
    source.write_text("\n".join(json.dumps({
        "units": float(index), "price": 10.0,
        "revenue": float(index * 5 + 10),
    }) for index in range(1, 101)), encoding="utf-8")
    planning = request()
    value = order(planning).model_dump(by_alias=True, mode="json")
    value["payload"]["whatIfAnalysis"] = {
        "objective": "MAXIMIZE_TARGET",
        "scenarios": [
            {"code": "UNITS_UP_10",
             "changes": [{"column": "units", "percentChange": 10}]},
            {"code": "UNITS_DOWN_10",
             "changes": [{"column": "units", "percentChange": -10}]},
        ],
    }
    governed_order = MlOrder.model_validate(value)
    validate_ml_order(governed_order, planning)

    result = asyncio.run(SparkMlExecutor(spark, MemoryMinio()).execute(
        uuid4(), governed_order,
        {"datasetUri": str(source), "datasetFormat": "json", "timeoutSeconds": 60},
        asyncio.Event()))

    chart = next(item for item in result["charts"]
                 if item["chartId"] == "what-if-analysis")
    facts = {item["code"]: item for item in chart["scenarioFacts"]}
    assert facts["UNITS_UP_10"]["deltaPercent"] > 0
    assert facts["UNITS_DOWN_10"]["deltaPercent"] < 0
    assert result["warnings"][0]["code"] == "WHAT_IF_NOT_CAUSAL"


def test_regression_pipeline_encodes_governed_categorical_features(tmp_path, spark):
    source = tmp_path / "categorical-sales.json"
    source.write_text("\n".join(json.dumps({
        "units": float(index),
        "price": float(2 + index % 3),
        "region": ("Marmara" if index % 2 else "Ege"),
        "revenue": float(index * 4 + (20 if index % 2 else 5)),
    }) for index in range(1, 81)), encoding="utf-8")
    planning = request()
    planning.authorized_schema.columns.append(
        planning.authorized_schema.columns[0].model_copy(
            update={
                "column_name": "region",
                "business_name": "Region",
                "data_type": "STRING",
            }
        )
    )
    value = order(planning).model_copy(deep=True)
    value.payload.algorithm = "DECISION_TREE_REGRESSOR"
    value.payload.parameters = {
        "maxDepth": 4, "minInstancesPerNode": 1, "minInfoGain": 0.0,
    }
    value.payload.feature_columns.append("region")
    value.payload.categorical_feature_columns = ["region"]
    store = MemoryMinio()

    result = asyncio.run(SparkMlExecutor(spark, store).execute(
        uuid4(), value,
        {"datasetUri": str(source), "datasetFormat": "json", "timeoutSeconds": 60},
        asyncio.Event()))

    assert result["rowCount"] > 0
    assert result["charts"]
    categories = result["charts"][0]["categories"]
    assert any(item.startswith("region: ") for item in categories)
    assert all("__kozmik_encoded_" not in item for item in categories)
    assert len(categories) == len(result["charts"][0]["series"][0]["data"])
    assert all(value > 0 for value in result["charts"][0]["series"][0]["data"])


@pytest.mark.parametrize(
    ("algorithm", "parameters"),
    [
        ("RANDOM_FOREST_CLASSIFIER", {"numTrees": 10, "maxDepth": 4, "seed": 42}),
        ("XGBOOST_CLASSIFIER", {"numRounds": 10, "maxDepth": 4, "seed": 42}),
    ],
)
def test_binary_classification_produces_probabilities_and_safe_aggregate_facts(
    tmp_path, spark, algorithm, parameters,
):
    source = tmp_path / f"{algorithm.lower()}.json"
    source.write_text("\n".join(json.dumps({
        "units": float(index),
        "price": float(index % 5),
        "revenue": float(1 if index + index % 5 > 35 else 0),
    }) for index in range(1, 81)), encoding="utf-8")
    value = order(request()).model_copy(deep=True)
    value.payload.problem_type = "BINARY_CLASSIFICATION"
    value.payload.algorithm = algorithm
    value.payload.parameters = parameters
    value.payload.metrics = ["ACCURACY", "F1", "AUC"]
    store = MemoryMinio()
    result = asyncio.run(SparkMlExecutor(spark, store).execute(
        uuid4(), value,
        {"datasetUri": str(source), "datasetFormat": "json", "timeoutSeconds": 120},
        asyncio.Event()))
    assert "positiveProbability" in {
        item["name"] for item in result["preview"]["columns"]
    }
    facts = {item["code"]: item for item in result["kpis"]}
    assert {"ACCURACY", "F1", "AUC", "AVERAGE_POSITIVE_PROBABILITY"}.issubset(facts)
    assert 0 <= facts["AVERAGE_POSITIVE_PROBABILITY"]["value"] <= 100
    assert facts["AVERAGE_POSITIVE_PROBABILITY"]["unit"] == "PERCENT"


def test_binary_threshold_target_is_created_inside_trusted_spark(
    tmp_path, spark,
):
    source = tmp_path / "derived-binary-target.json"
    source.write_text("\n".join(json.dumps({
        "units": float(index),
        "price": float(index % 5),
        "revenue": float(index + index % 5),
    }) for index in range(1, 81)), encoding="utf-8")
    value = order(request()).model_dump(by_alias=True, mode="json")
    value["payload"].update({
        "problemType": "BINARY_CLASSIFICATION",
        "algorithm": "LOGISTIC_REGRESSION",
        "targetColumn": "high_revenue",
        "binaryTargetDerivation": {
            "sourceColumn": "revenue", "operator": "GT", "threshold": 35,
        },
        "parameters": {"maxIter": 30, "regParam": 0.0},
        "metrics": ["ACCURACY", "F1", "AUC"],
    })
    governed = MlOrder.model_validate(value)
    store = MemoryMinio()

    result = asyncio.run(SparkMlExecutor(spark, store).execute(
        uuid4(), governed,
        {"datasetUri": str(source), "datasetFormat": "json", "timeoutSeconds": 120},
        asyncio.Event()))

    assert {row["high_revenue"] for row in result["preview"]["rows"]} <= {0.0, 1.0}
    assert "positiveProbability" in {
        item["name"] for item in result["preview"]["columns"]
    }


def test_boolean_binary_target_is_cast_inside_trusted_spark(tmp_path, spark):
    source = tmp_path / "boolean-binary-target.json"
    source.write_text("\n".join(json.dumps({
        "units": float(index),
        "price": float(index % 7),
        "revenue": float(index + index % 7),
        "is_fraud": index % 5 == 0,
    }) for index in range(1, 101)), encoding="utf-8")
    value = order(request()).model_dump(by_alias=True, mode="json")
    value["payload"].update({
        "problemType": "BINARY_CLASSIFICATION",
        "algorithm": "LOGISTIC_REGRESSION",
        "targetColumn": "is_fraud",
        "parameters": {"maxIter": 30, "regParam": 0.0},
        "metrics": ["ACCURACY", "F1", "AUC"],
    })
    governed = MlOrder.model_validate(value)

    result = asyncio.run(SparkMlExecutor(spark, MemoryMinio()).execute(
        uuid4(), governed,
        {"datasetUri": str(source), "datasetFormat": "json", "timeoutSeconds": 120},
        asyncio.Event()))

    assert {row["is_fraud"] for row in result["preview"]["rows"]} <= {0.0, 1.0}
    assert "positiveProbability" in {
        item["name"] for item in result["preview"]["columns"]
    }


def test_bounded_candidate_pipeline_selects_best_model_on_validation_data(
    tmp_path, spark,
):
    source = tmp_path / "tuned-regression.json"
    source.write_text("\n".join(json.dumps({
        "units": float(index),
        "price": float(2 + index % 3),
        "revenue": float(index * 4 + (2 + index % 3) * 3),
    }) for index in range(1, 121)), encoding="utf-8")
    store = MemoryMinio()
    result = asyncio.run(SparkMlExecutor(spark, store).execute(
        uuid4(), tuned_order(request()),
        {"datasetUri": str(source), "datasetFormat": "json", "timeoutSeconds": 120},
        asyncio.Event()))
    facts = {item["code"]: item["value"] for item in result["kpis"]}
    assert facts["SELECTED_ALGORITHM"] == "LINEAR_REGRESSION"
    assert facts["TUNING_TRIALS_EVALUATED"] == 3
    assert facts["CANDIDATE_ALGORITHMS_EVALUATED"] == 2
    assert facts["BEST_VALIDATION_SCORE"] >= 0
    assert {"RMSE", "R2"}.issubset(facts)
    assert {bucket for bucket, _ in store.uploads} == {"results", "models"}
