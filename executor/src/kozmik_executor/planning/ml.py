from kozmik_executor.planning.models import (
    DataType,
    MlOrder,
    ReportPlanningRequest,
    ValidationIssue,
)
from kozmik_executor.planning.validation import PlanningValidationError
from kozmik_executor.planning.registries import FILTER_TYPES

NUMERIC = {DataType.INTEGER, DataType.LONG, DataType.DECIMAL}
BINARY_TARGET_TYPES = NUMERIC | {DataType.BOOLEAN}
REGRESSION_METRICS = {"RMSE", "MAE", "R2"}
CLASSIFICATION_METRICS = {"ACCURACY", "F1", "PRECISION", "RECALL", "AUC"}
TREE_PARAMETERS = {
    # Tree depth grows the serialized model exponentially.
    "maxDepth": (1, 15),
    "minInstancesPerNode": (1, 1000),
    "minInfoGain": (0.0, 1000.0),
}
FOREST_PARAMETERS = {
    **TREE_PARAMETERS,
    "numTrees": (1, 500),
    "featureSubsetStrategy": {
        "auto", "all", "onethird", "sqrt", "log2",
    },
    "subsamplingRate": (0.1, 1.0),
    "seed": (0, 2_147_483_647),
}
GBT_PARAMETERS = {
    **TREE_PARAMETERS,
    # Larger values can create a Scala model graph deep enough to overflow
    # Spark's task serializer on the shared executor.
    "maxIter": (1, 50),
    "stepSize": (0.001, 1.0),
    "subsamplingRate": (0.1, 1.0),
    "seed": (0, 2_147_483_647),
}
XGBOOST_PARAMETERS = {
    "maxDepth": (1, 30),
    "numRounds": (1, 1000),
    "learningRate": (0.001, 1.0),
    "minChildWeight": (0.0, 1000.0),
    "subsample": (0.1, 1.0),
    "colsampleBytree": (0.1, 1.0),
    "regAlpha": (0.0, 1000.0),
    "regLambda": (0.0, 1000.0),
    "seed": (0, 2_147_483_647),
}
ALGORITHM_REGISTRY = {
    ("REGRESSION", "LINEAR_REGRESSION"): {
        "parameters": {"maxIter": (1, 200), "regParam": (0.0, 10.0)},
        "metrics": REGRESSION_METRICS,
    },
    ("BINARY_CLASSIFICATION", "LOGISTIC_REGRESSION"): {
        "parameters": {"maxIter": (1, 200), "regParam": (0.0, 10.0)},
        "metrics": CLASSIFICATION_METRICS,
    },
    ("REGRESSION", "DECISION_TREE_REGRESSOR"): {
        "parameters": TREE_PARAMETERS, "metrics": REGRESSION_METRICS,
    },
    ("BINARY_CLASSIFICATION", "DECISION_TREE_CLASSIFIER"): {
        "parameters": TREE_PARAMETERS, "metrics": CLASSIFICATION_METRICS,
    },
    ("REGRESSION", "RANDOM_FOREST_REGRESSOR"): {
        "parameters": FOREST_PARAMETERS, "metrics": REGRESSION_METRICS,
    },
    ("BINARY_CLASSIFICATION", "RANDOM_FOREST_CLASSIFIER"): {
        "parameters": FOREST_PARAMETERS, "metrics": CLASSIFICATION_METRICS,
    },
    ("REGRESSION", "GBT_REGRESSOR"): {
        "parameters": GBT_PARAMETERS, "metrics": REGRESSION_METRICS,
    },
    ("BINARY_CLASSIFICATION", "GBT_CLASSIFIER"): {
        "parameters": GBT_PARAMETERS, "metrics": CLASSIFICATION_METRICS,
    },
    ("REGRESSION", "XGBOOST_REGRESSOR"): {
        "parameters": XGBOOST_PARAMETERS, "metrics": REGRESSION_METRICS,
    },
    ("BINARY_CLASSIFICATION", "XGBOOST_CLASSIFIER"): {
        "parameters": XGBOOST_PARAMETERS, "metrics": CLASSIFICATION_METRICS,
    },
}


def _parameter_allowed(rule, value) -> bool:
    return (
        isinstance(rule, tuple)
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
        and rule[0] <= value <= rule[1]
    ) or (
        isinstance(rule, set)
        and isinstance(value, str)
        and value in rule
    )


def validate_ml_order(order: MlOrder, request: ReportPlanningRequest) -> None:
    issues = []
    if not set(request.capabilities).intersection({"SCIENTIST", "ADMIN"}):
        issues.append(ValidationIssue(code="ROLE_NOT_AUTHORIZED", path="capabilities",
                                      message="Scientist capability is required"))
    if order.entity_id != request.authorized_schema.entity_id:
        issues.append(ValidationIssue(code="ENTITY_MISMATCH", path="entityId",
                                      message="Entity is not authorized"))
    columns = {column.column_name: column for column in request.authorized_schema.columns}
    target = columns.get(order.payload.target_column)
    derivation = order.payload.binary_target_derivation
    allowed_target_types = (
        BINARY_TARGET_TYPES
        if order.payload.problem_type == "BINARY_CLASSIFICATION"
        else NUMERIC
    )
    if derivation is None and (
        target is None or target.data_type not in allowed_target_types
    ):
        issues.append(ValidationIssue(code="TARGET_NOT_ALLOWED", path="payload.targetColumn",
                                      message=(
                                          "Regression targets must be numeric; binary "
                                          "classification targets may be numeric or boolean"
                                      )))
    if derivation is not None:
        source = columns.get(derivation.source_column)
        if order.payload.problem_type != "BINARY_CLASSIFICATION":
            issues.append(ValidationIssue(
                code="DERIVED_TARGET_REQUIRES_BINARY_CLASSIFICATION",
                path="payload.binaryTargetDerivation",
                message="A derived threshold target requires binary classification",
            ))
        if target is not None:
            issues.append(ValidationIssue(
                code="DERIVED_TARGET_COLLIDES_WITH_SOURCE_SCHEMA",
                path="payload.targetColumn",
                message="A derived target name must not replace an existing source column",
            ))
        if source is None or source.data_type not in NUMERIC:
            issues.append(ValidationIssue(
                code="DERIVED_TARGET_SOURCE_NOT_ALLOWED",
                path="payload.binaryTargetDerivation.sourceColumn",
                message="A derived target requires an authorized numeric source column",
            ))
        if derivation.source_column in order.payload.feature_columns:
            issues.append(ValidationIssue(
                code="DERIVED_TARGET_SOURCE_IS_FEATURE",
                path="payload.featureColumns",
                message="The source used to derive the target cannot also be a feature",
            ))
    if len(set(order.payload.feature_columns)) != len(order.payload.feature_columns):
        issues.append(ValidationIssue(code="DUPLICATE_FEATURE", path="payload.featureColumns",
                                      message="Features must be unique"))
    if order.payload.target_column in order.payload.feature_columns:
        issues.append(ValidationIssue(code="TARGET_IS_FEATURE", path="payload.featureColumns",
                                      message="Target cannot also be a feature"))
    for index, name in enumerate(order.payload.feature_columns):
        column = columns.get(name)
        if (
            column is None
        ):
            issues.append(ValidationIssue(code="FEATURE_NOT_ALLOWED",
                                          path=f"payload.featureColumns[{index}]",
                                          message="Feature must be an eligible governed column"))
        elif column.data_type not in NUMERIC | {DataType.STRING}:
            issues.append(ValidationIssue(
                code="FEATURE_TYPE_NOT_SUPPORTED",
                path=f"payload.featureColumns[{index}]",
                message="Feature must be numeric or categorical text",
            ))
    expected_categorical = {
        name for name in order.payload.feature_columns
        if columns.get(name) is not None and columns[name].data_type == DataType.STRING
    }
    if set(order.payload.categorical_feature_columns) != expected_categorical:
        issues.append(ValidationIssue(
            code="CATEGORICAL_FEATURES_MISMATCH",
            path="payload.categoricalFeatureColumns",
            message="Categorical features must match the authorized schema",
        ))
    if order.payload.what_if_analysis is not None:
        if order.payload.problem_type != "REGRESSION":
            issues.append(ValidationIssue(
                code="WHAT_IF_PROBLEM_TYPE_NOT_SUPPORTED",
                path="payload.whatIfAnalysis",
                message="What-if analysis currently supports regression only",
            ))
        scenario_codes = set()
        for scenario_index, scenario in enumerate(
            order.payload.what_if_analysis.scenarios
        ):
            if scenario.code in scenario_codes:
                issues.append(ValidationIssue(
                    code="DUPLICATE_WHAT_IF_SCENARIO",
                    path=f"payload.whatIfAnalysis.scenarios[{scenario_index}].code",
                    message="What-if scenario codes must be unique",
                ))
            scenario_codes.add(scenario.code)
            changed_columns = set()
            for change_index, change in enumerate(scenario.changes):
                column = columns.get(change.column)
                path = (
                    f"payload.whatIfAnalysis.scenarios[{scenario_index}]"
                    f".changes[{change_index}].column"
                )
                if change.column in changed_columns:
                    issues.append(ValidationIssue(
                        code="DUPLICATE_WHAT_IF_COLUMN", path=path,
                        message="A scenario may change each feature only once",
                    ))
                changed_columns.add(change.column)
                if (
                    change.column not in order.payload.feature_columns
                    or column is None
                    or column.data_type not in NUMERIC
                ):
                    issues.append(ValidationIssue(
                        code="WHAT_IF_COLUMN_NOT_ALLOWED", path=path,
                        message="What-if changes require an approved numeric feature",
                    ))
    for index, item in enumerate(order.payload.filters):
        column = columns.get(item.column)
        if (
            column is None
            or column.data_type not in NUMERIC
        ):
            issues.append(ValidationIssue(
                code="FILTER_COLUMN_NOT_ALLOWED",
                path=f"payload.filters[{index}].column",
                message="Filter column must be report eligible",
            ))
            continue
        allowed_types = FILTER_TYPES.get(item.operator)
        if allowed_types is not None and column.data_type not in allowed_types:
            issues.append(ValidationIssue(
                code="OPERATOR_TYPE_MISMATCH",
                path=f"payload.filters[{index}].operator",
                message="Operator is not approved for the filter column type",
            ))
    definition = ALGORITHM_REGISTRY.get(
        (order.payload.problem_type, order.payload.algorithm))
    if definition is None:
        issues.append(ValidationIssue(code="ALGORITHM_NOT_ALLOWED", path="payload.algorithm",
                                      message="Algorithm is not registered for problem type"))
    else:
        if not set(order.payload.metrics).issubset(definition["metrics"]):
            issues.append(ValidationIssue(code="METRIC_NOT_ALLOWED", path="payload.metrics",
                                          message="Metric is not registered"))
        for name, value in order.payload.parameters.items():
            bounds = definition["parameters"].get(name)
            if not _parameter_allowed(bounds, value):
                issues.append(ValidationIssue(code="PARAMETER_NOT_ALLOWED",
                                              path=f"payload.parameters.{name}",
                                              message="Parameter is outside approved bounds"))
    if order.payload.candidate_algorithms:
        seen = set()
        total_trials = 0
        selection = order.payload.selection
        if selection.primary_metric not in order.payload.metrics:
            issues.append(ValidationIssue(
                code="SELECTION_METRIC_NOT_RETURNED",
                path="payload.metrics",
                message="Primary selection metric must be included in final metrics",
            ))
        for index, candidate in enumerate(order.payload.candidate_algorithms):
            if candidate.algorithm in seen:
                issues.append(ValidationIssue(
                    code="DUPLICATE_ALGORITHM",
                    path=f"payload.candidateAlgorithms[{index}].algorithm",
                    message="Candidate algorithms must be unique",
                ))
            seen.add(candidate.algorithm)
            candidate_definition = ALGORITHM_REGISTRY.get(
                (order.payload.problem_type, candidate.algorithm))
            if candidate_definition is None:
                issues.append(ValidationIssue(
                    code="ALGORITHM_NOT_ALLOWED",
                    path=f"payload.candidateAlgorithms[{index}].algorithm",
                    message="Candidate is not registered for the problem type",
                ))
                continue
            if selection.primary_metric not in candidate_definition["metrics"]:
                issues.append(ValidationIssue(
                    code="METRIC_NOT_ALLOWED",
                    path="payload.selection.primaryMetric",
                    message="Primary metric must be supported by every candidate",
                ))
            combinations = 1
            for name, values in candidate.parameter_grid.items():
                rule = candidate_definition["parameters"].get(name)
                if not values or len(values) > 10:
                    issues.append(ValidationIssue(
                        code="PARAMETER_GRID_INVALID",
                        path=f"payload.candidateAlgorithms[{index}].parameterGrid.{name}",
                        message="Parameter grid values must contain between 1 and 10 items",
                    ))
                    continue
                combinations *= len(values)
                for value in values:
                    if not _parameter_allowed(rule, value):
                        issues.append(ValidationIssue(
                            code="PARAMETER_NOT_ALLOWED",
                            path=(
                                f"payload.candidateAlgorithms[{index}]"
                                f".parameterGrid.{name}"
                            ),
                            message="Candidate parameter is outside approved bounds",
                        ))
            total_trials += combinations
        if total_trials > selection.maximum_trials:
            issues.append(ValidationIssue(
                code="TRIAL_BUDGET_EXCEEDED",
                path="payload.selection.maximumTrials",
                message="Candidate grid exceeds the approved trial budget",
            ))
    if issues:
        raise PlanningValidationError(issues)


ML_SYSTEM_PROMPT = """Return one versioned JSON ML order only.
Select algorithms only from the supplied governed registry and only when compatible with the
problem type, authorized schema, metrics, and parameter ranges. When model comparison is useful,
return bounded candidateAlgorithms parameter grids plus a TRAIN_VALIDATION_SPLIT selection policy.
Never exceed 50 proposed trials. Prefer the simplest suitable candidates unless the objective
justifies tree, ensemble, gradient-boosted, or XGBoost models. Choose representative tuning
values inside the approved ranges; do not mechanically use the minimum and maximum bounds.
For an existing authorized BOOLEAN outcome column, use BINARY_CLASSIFICATION and preserve that
exact columnName as targetColumn. A BOOLEAN target is already binary; do not invent an alias or
binaryTargetDerivation for it.
When the user asks which records are likely to exceed or fall below a numeric threshold, use
BINARY_CLASSIFICATION with binaryTargetDerivation. Set sourceColumn to the authorized numeric
column, operator to GT, GTE, LT, or LTE, threshold to the requested numeric boundary, and use a
new targetColumn alias that does not collide with the source schema. Never include sourceColumn
in featureColumns because that would leak the answer into the model.
When the user asks whether management should increase, decrease, change, adjust, maintain,
expand, or limit numeric inputs, include whatIfAnalysis. Use MAXIMIZE_TARGET or MINIMIZE_TARGET
as requested and provide at most six bounded scenarios. Prefer paired one-variable percentage
changes so direction can be compared. Percent changes must remain between -25 and 25. What-if
scenarios are governed prediction comparisons, not causal claims. The unchanged baseline is
calculated automatically by Spark: never include BASELINE, UNCHANGED, or a zero-change scenario
inside whatIfAnalysis.scenarios.
Never return SQL, Python,
executable code, paths, raw rows, or source text."""
