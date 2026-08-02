from enum import StrEnum
from typing import Literal

from kozmik_executor.chat.models import ContractModel


class SemanticKey(StrEnum):
    SUM = "SUM"
    COUNT = "COUNT"
    COUNT_DISTINCT = "COUNT_DISTINCT"
    AVG = "AVG"
    MIN = "MIN"
    MAX = "MAX"
    ABSOLUTE_DIFFERENCE = "ABSOLUTE_DIFFERENCE"
    SYMMETRIC_RELATIVE_SPREAD = "SYMMETRIC_RELATIVE_SPREAD"
    SHARE_OF_TOTAL = "SHARE_OF_TOTAL"
    TIME_PERCENTAGE_CHANGE = "TIME_PERCENTAGE_CHANGE"
    NORMALIZED_PER_DENOMINATOR = "NORMALIZED_PER_DENOMINATOR"
    MAE = "MAE"
    RMSE = "RMSE"
    R2 = "R2"
    ACCURACY = "ACCURACY"
    PRECISION = "PRECISION"
    RECALL = "RECALL"
    SPECIFICITY = "SPECIFICITY"
    F1 = "F1"
    AUC = "AUC"
    BASELINE_ACCURACY = "BASELINE_ACCURACY"
    SAMPLE_COUNT = "SAMPLE_COUNT"
    VALIDATION_SCORE = "VALIDATION_SCORE"
    TEST_SCORE = "TEST_SCORE"
    FEATURE_IMPORTANCE = "FEATURE_IMPORTANCE"
    SCENARIO_DELTA = "SCENARIO_DELTA"
    PREDICTED_RATE = "PREDICTED_RATE"
    ACTUAL_RATE = "ACTUAL_RATE"
    AVERAGE_MODEL_SCORE = "AVERAGE_MODEL_SCORE"
    RESULT_CARDINALITY = "RESULT_CARDINALITY"


class ValueKind(StrEnum):
    COUNT = "COUNT"
    AMOUNT = "AMOUNT"
    AVERAGE = "AVERAGE"
    RATIO = "RATIO"
    PERCENTAGE = "PERCENTAGE"
    ERROR_MAGNITUDE = "ERROR_MAGNITUDE"
    VARIATION_MEASURE = "VARIATION_MEASURE"
    RANKING_MEASURE = "RANKING_MEASURE"
    CLASSIFICATION_RATE = "CLASSIFICATION_RATE"
    SAMPLE_SIZE = "SAMPLE_SIZE"
    MODEL_SELECTION_SCORE = "MODEL_SELECTION_SCORE"
    IMPORTANCE_MAGNITUDE = "IMPORTANCE_MAGNITUDE"
    SCENARIO_DIFFERENCE = "SCENARIO_DIFFERENCE"


class UnitBehavior(StrEnum):
    EXPLICIT_ONLY = "EXPLICIT_ONLY"
    COUNT = "COUNT"
    PERCENT = "PERCENT"
    INHERIT_TARGET_UNIT = "INHERIT_TARGET_UNIT"
    NUMERATOR_PER_DENOMINATOR = "NUMERATOR_PER_DENOMINATOR"
    METRIC_DEPENDENT = "METRIC_DEPENDENT"


class SemanticDefinition(ContractModel):
    key: SemanticKey
    canonical_business_meaning: str
    execution_types: tuple[Literal["REPORT", "ML"], ...]
    problem_types: tuple[str, ...] = ()
    valid_scopes: tuple[str, ...]
    value_kind: ValueKind
    unit_behavior: UnitBehavior
    inherent_directionality: Literal[
        "CONTEXT_DEPENDENT", "HIGHER_IS_BETTER", "LOWER_IS_BETTER", "NEUTRAL"
    ]
    permitted_interpretations: tuple[str, ...]
    forbidden_interpretations: tuple[str, ...]
    required_context: tuple[str, ...] = ()
    comparisons_allowed: bool
    recommendations_allowed: bool = False
    directional_business_claims_allowed: bool = False
    qualitative_assessment_requires_context: bool = False


def _definition(
    key: SemanticKey,
    meaning: str,
    execution_types: tuple[Literal["REPORT", "ML"], ...],
    scopes: tuple[str, ...],
    value_kind: ValueKind,
    unit_behavior: UnitBehavior,
    directionality: Literal[
        "CONTEXT_DEPENDENT", "HIGHER_IS_BETTER", "LOWER_IS_BETTER", "NEUTRAL"
    ],
    permitted: tuple[str, ...],
    forbidden: tuple[str, ...],
    *,
    problem_types: tuple[str, ...] = (),
    required_context: tuple[str, ...] = (),
    comparisons_allowed: bool = True,
    recommendations_allowed: bool = False,
    directional_business_claims_allowed: bool = False,
    qualitative_assessment_requires_context: bool = False,
) -> SemanticDefinition:
    return SemanticDefinition(
        key=key,
        canonicalBusinessMeaning=meaning,
        executionTypes=execution_types,
        problemTypes=problem_types,
        validScopes=scopes,
        valueKind=value_kind,
        unitBehavior=unit_behavior,
        inherentDirectionality=directionality,
        permittedInterpretations=permitted,
        forbiddenInterpretations=forbidden,
        requiredContext=required_context,
        comparisonsAllowed=comparisons_allowed,
        recommendationsAllowed=recommendations_allowed,
        directionalBusinessClaimsAllowed=directional_business_claims_allowed,
        qualitativeAssessmentRequiresContext=qualitative_assessment_requires_context,
    )


REPORT_COMPLETE = ("COMPLETE_RESULT",)
REPORT_MEASURE_SCOPES = ("COMPLETE_RESULT", "BOUNDED_CHART_DATA")
ML_TEST = ("UNTOUCHED_TEST_DATA",)


SEMANTIC_REGISTRY: dict[SemanticKey, SemanticDefinition] = {
    SemanticKey.SUM: _definition(
        SemanticKey.SUM, "The calculated total of the governed measure.", ("REPORT",),
        REPORT_MEASURE_SCOPES, ValueKind.AMOUNT, UnitBehavior.EXPLICIT_ONLY,
        "CONTEXT_DEPENDENT", ("total", "calculated sum"),
        ("automatically better", "automatically worse", "unrelated business measure"),
    ),
    SemanticKey.COUNT: _definition(
        SemanticKey.COUNT, "The number of records in the stated scope.", ("REPORT",),
        REPORT_MEASURE_SCOPES, ValueKind.COUNT, UnitBehavior.COUNT, "CONTEXT_DEPENDENT",
        ("record count", "number of records"),
        ("automatically better", "automatically worse", "percentage"),
    ),
    SemanticKey.COUNT_DISTINCT: _definition(
        SemanticKey.COUNT_DISTINCT,
        "The number of distinct governed values in the stated scope.", ("REPORT",),
        REPORT_MEASURE_SCOPES, ValueKind.COUNT, UnitBehavior.COUNT, "CONTEXT_DEPENDENT",
        ("distinct count",), ("ordinary row count", "percentage"),
    ),
    SemanticKey.AVG: _definition(
        SemanticKey.AVG, "The arithmetic average of the governed measure.", ("REPORT",),
        REPORT_MEASURE_SCOPES, ValueKind.AVERAGE, UnitBehavior.EXPLICIT_ONLY,
        "CONTEXT_DEPENDENT", ("average", "mean"),
        ("total", "automatically better", "automatically worse"),
    ),
    SemanticKey.MIN: _definition(
        SemanticKey.MIN, "The lowest recorded value in the stated scope.", ("REPORT",),
        REPORT_MEASURE_SCOPES, ValueKind.AMOUNT, UnitBehavior.EXPLICIT_ONLY,
        "CONTEXT_DEPENDENT", ("lowest recorded value",), ("worst", "weakest"),
    ),
    SemanticKey.MAX: _definition(
        SemanticKey.MAX, "The highest recorded value in the stated scope.", ("REPORT",),
        REPORT_MEASURE_SCOPES, ValueKind.AMOUNT, UnitBehavior.EXPLICIT_ONLY,
        "CONTEXT_DEPENDENT", ("highest recorded value",), ("best", "strongest"),
    ),
    SemanticKey.ABSOLUTE_DIFFERENCE: _definition(
        SemanticKey.ABSOLUTE_DIFFERENCE,
        "The arithmetic distance between two explicitly scoped values.", ("REPORT",),
        REPORT_COMPLETE, ValueKind.AMOUNT, UnitBehavior.EXPLICIT_ONLY,
        "NEUTRAL", ("absolute difference", "absolute spread"),
        ("growth", "share", "improvement", "deterioration"),
    ),
    SemanticKey.SYMMETRIC_RELATIVE_SPREAD: _definition(
        SemanticKey.SYMMETRIC_RELATIVE_SPREAD,
        "The absolute distance between two values divided by their average magnitude.",
        ("REPORT",), REPORT_COMPLETE, ValueKind.PERCENTAGE, UnitBehavior.PERCENT,
        "NEUTRAL", ("relative spread between the stated values",),
        ("growth", "decline", "percentage change", "share of total", "improvement"),
    ),
    SemanticKey.SHARE_OF_TOTAL: _definition(
        SemanticKey.SHARE_OF_TOTAL,
        "The stated part divided by the complete positive total for the same measure.",
        ("REPORT",), REPORT_COMPLETE, ValueKind.PERCENTAGE, UnitBehavior.PERCENT,
        "CONTEXT_DEPENDENT", ("share of total", "proportion of total"),
        ("growth", "percentage change", "relative spread"),
    ),
    SemanticKey.TIME_PERCENTAGE_CHANGE: _definition(
        SemanticKey.TIME_PERCENTAGE_CHANGE,
        "The later value minus the earlier value, divided by the absolute earlier value.",
        ("REPORT",), REPORT_COMPLETE, ValueKind.PERCENTAGE, UnitBehavior.PERCENT,
        "CONTEXT_DEPENDENT", ("change from the stated earlier period to the later period",),
        ("share of total", "relative spread", "causal effect"),
    ),
    SemanticKey.NORMALIZED_PER_DENOMINATOR: _definition(
        SemanticKey.NORMALIZED_PER_DENOMINATOR,
        "The governed numerator divided by its governed denominator in the same scope.",
        ("REPORT",), REPORT_COMPLETE, ValueKind.RATIO,
        UnitBehavior.NUMERATOR_PER_DENOMINATOR, "CONTEXT_DEPENDENT",
        ("numerator per denominator", "normalized ratio"),
        ("raw total", "cost", "profit", "automatically better"),
    ),
    SemanticKey.MAE: _definition(
        SemanticKey.MAE,
        "The mean absolute difference between predicted and observed target values.",
        ("ML",), ML_TEST, ValueKind.ERROR_MAGNITUDE, UnitBehavior.INHERIT_TARGET_UNIT,
        "LOWER_IS_BETTER", ("average absolute prediction difference",),
        ("accuracy", "confidence", "probability", "percentage"),
        problem_types=("REGRESSION",), qualitative_assessment_requires_context=True,
    ),
    SemanticKey.RMSE: _definition(
        SemanticKey.RMSE,
        "The square root of mean squared prediction error; larger errors have more influence.",
        ("ML",), ML_TEST, ValueKind.ERROR_MAGNITUDE, UnitBehavior.INHERIT_TARGET_UNIT,
        "LOWER_IS_BETTER", ("larger-error-sensitive prediction difference",),
        ("average error magnitude", "accuracy", "confidence", "probability", "percentage"),
        problem_types=("REGRESSION",), qualitative_assessment_requires_context=True,
    ),
    SemanticKey.R2: _definition(
        SemanticKey.R2,
        "The proportion of target variation captured on the stated evaluation data.",
        ("ML",), ML_TEST, ValueKind.VARIATION_MEASURE, UnitBehavior.PERCENT,
        "HIGHER_IS_BETTER", ("variation captured",),
        ("accuracy", "confidence", "probability", "reliability"),
        problem_types=("REGRESSION",), qualitative_assessment_requires_context=True,
    ),
    SemanticKey.ACCURACY: _definition(
        SemanticKey.ACCURACY,
        "The share of all evaluated cases classified correctly.", ("ML",), ML_TEST,
        ValueKind.CLASSIFICATION_RATE, UnitBehavior.PERCENT, "HIGHER_IS_BETTER",
        ("overall evaluated-case correctness",), ("confidence", "probability"),
        problem_types=("BINARY_CLASSIFICATION",), required_context=("BASELINE_ACCURACY",),
        qualitative_assessment_requires_context=True,
    ),
    SemanticKey.PRECISION: _definition(
        SemanticKey.PRECISION,
        "The share of predicted cases in the stated class scope that were observed in that class.",
        ("ML",), ML_TEST, ValueKind.CLASSIFICATION_RATE, UnitBehavior.PERCENT,
        "HIGHER_IS_BETTER", ("flagged-case correctness for the stated class scope",),
        ("recall", "confidence", "probability"), problem_types=("BINARY_CLASSIFICATION",),
        qualitative_assessment_requires_context=True,
    ),
    SemanticKey.RECALL: _definition(
        SemanticKey.RECALL,
        "The share of observed cases in the stated class scope that were identified.",
        ("ML",), ML_TEST, ValueKind.CLASSIFICATION_RATE, UnitBehavior.PERCENT,
        "HIGHER_IS_BETTER", ("observed-case coverage for the stated class scope",),
        ("precision", "confidence", "probability"), problem_types=("BINARY_CLASSIFICATION",),
        qualitative_assessment_requires_context=True,
    ),
    SemanticKey.SPECIFICITY: _definition(
        SemanticKey.SPECIFICITY,
        "The share of actual negative cases correctly left unflagged.", ("ML",), ML_TEST,
        ValueKind.CLASSIFICATION_RATE, UnitBehavior.PERCENT, "HIGHER_IS_BETTER",
        ("negative-case exclusion",), ("positive-case recall", "confidence"),
        problem_types=("BINARY_CLASSIFICATION",), qualitative_assessment_requires_context=True,
    ),
    SemanticKey.F1: _definition(
        SemanticKey.F1,
        "The harmonic balance of precision and recall for the stated averaging scope.",
        ("ML",), ML_TEST, ValueKind.CLASSIFICATION_RATE, UnitBehavior.PERCENT,
        "HIGHER_IS_BETTER", ("precision-recall balance",),
        ("accuracy", "confidence", "probability"), problem_types=("BINARY_CLASSIFICATION",),
        qualitative_assessment_requires_context=True,
    ),
    SemanticKey.AUC: _definition(
        SemanticKey.AUC,
        "The model's ability to rank positive cases above negative cases across thresholds.",
        ("ML",), ML_TEST, ValueKind.RANKING_MEASURE, UnitBehavior.PERCENT,
        "HIGHER_IS_BETTER", ("ranking separation",),
        ("accuracy", "confidence", "probability", "individual prediction likelihood"),
        problem_types=("BINARY_CLASSIFICATION",), qualitative_assessment_requires_context=True,
    ),
    SemanticKey.BASELINE_ACCURACY: _definition(
        SemanticKey.BASELINE_ACCURACY,
        "Correctness obtained by always choosing the most common evaluated class.",
        ("ML",), ML_TEST, ValueKind.CLASSIFICATION_RATE, UnitBehavior.PERCENT,
        "NEUTRAL", ("majority-class baseline",), ("selected model accuracy",),
        problem_types=("BINARY_CLASSIFICATION",),
    ),
    SemanticKey.SAMPLE_COUNT: _definition(
        SemanticKey.SAMPLE_COUNT, "The number of cases in the stated evaluation scope.",
        ("ML",), ML_TEST, ValueKind.SAMPLE_SIZE, UnitBehavior.COUNT, "NEUTRAL",
        ("evaluated case count",), ("accuracy", "percentage"), comparisons_allowed=False,
    ),
    SemanticKey.VALIDATION_SCORE: _definition(
        SemanticKey.VALIDATION_SCORE,
        "The metric value used only to select a candidate using validation data.",
        ("ML",), ("VALIDATION_DATA_ONLY",), ValueKind.MODEL_SELECTION_SCORE,
        UnitBehavior.METRIC_DEPENDENT, "NEUTRAL", ("candidate-selection score",),
        ("final performance", "test performance", "production performance"),
        comparisons_allowed=True,
    ),
    SemanticKey.TEST_SCORE: _definition(
        SemanticKey.TEST_SCORE,
        "A metric measured on untouched test data after model selection.", ("ML",),
        ML_TEST, ValueKind.MODEL_SELECTION_SCORE, UnitBehavior.METRIC_DEPENDENT,
        "NEUTRAL", ("final evaluation measurement",),
        ("validation score", "training score"), comparisons_allowed=True,
    ),
    SemanticKey.FEATURE_IMPORTANCE: _definition(
        SemanticKey.FEATURE_IMPORTANCE,
        "A model-specific magnitude showing how heavily the selected model relied on a field.",
        ("ML",), ("SELECTED_MODEL",), ValueKind.IMPORTANCE_MAGNITUDE,
        UnitBehavior.EXPLICIT_ONLY, "NEUTRAL", ("model reliance magnitude",),
        ("positive effect", "negative effect", "causality", "contribution to accuracy"),
        comparisons_allowed=True,
    ),
    SemanticKey.SCENARIO_DELTA: _definition(
        SemanticKey.SCENARIO_DELTA,
        "The calculated difference between an executed controlled scenario and its baseline.",
        ("ML",), ("SCENARIO_COMPARISON",), ValueKind.SCENARIO_DIFFERENCE,
        UnitBehavior.PERCENT, "CONTEXT_DEPENDENT",
        ("conditional calculated scenario difference",),
        ("causal effect", "guaranteed outcome", "unmeasured business impact"),
        recommendations_allowed=True, directional_business_claims_allowed=True,
    ),
    SemanticKey.PREDICTED_RATE: _definition(
        SemanticKey.PREDICTED_RATE,
        "The share of evaluated cases assigned to the stated predicted class.",
        ("ML",), ML_TEST, ValueKind.CLASSIFICATION_RATE, UnitBehavior.PERCENT,
        "NEUTRAL", ("predicted class share",), ("actual class share", "accuracy"),
        problem_types=("BINARY_CLASSIFICATION",),
    ),
    SemanticKey.ACTUAL_RATE: _definition(
        SemanticKey.ACTUAL_RATE,
        "The observed share of evaluated cases belonging to the stated class.",
        ("ML",), ML_TEST, ValueKind.CLASSIFICATION_RATE, UnitBehavior.PERCENT,
        "NEUTRAL", ("observed class share",), ("predicted class share", "accuracy"),
        problem_types=("BINARY_CLASSIFICATION",),
    ),
    SemanticKey.AVERAGE_MODEL_SCORE: _definition(
        SemanticKey.AVERAGE_MODEL_SCORE,
        "The average model-produced positive-class score across evaluated cases.",
        ("ML",), ML_TEST, ValueKind.PERCENTAGE, UnitBehavior.PERCENT, "NEUTRAL",
        ("average model score",), ("individual confidence", "accuracy"),
        problem_types=("BINARY_CLASSIFICATION",),
    ),
    SemanticKey.RESULT_CARDINALITY: _definition(
        SemanticKey.RESULT_CARDINALITY,
        "The number of rows in the analytical result, which may represent groups or predictions "
        "and is not automatically the number of source records.",
        ("REPORT", "ML"), ("COMPLETE_RESULT",), ValueKind.SAMPLE_SIZE,
        UnitBehavior.COUNT, "NEUTRAL", ("analytical result row count",),
        ("source record count", "input data size"), comparisons_allowed=False,
    ),
}


def semantic_definition(key: SemanticKey | str) -> SemanticDefinition:
    return SEMANTIC_REGISTRY[SemanticKey(key)]
