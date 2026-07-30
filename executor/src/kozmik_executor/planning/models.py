from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, model_validator

from kozmik_executor.chat.models import ContractModel


class DataType(StrEnum):
    STRING = "STRING"
    INTEGER = "INTEGER"
    LONG = "LONG"
    DECIMAL = "DECIMAL"
    BOOLEAN = "BOOLEAN"
    DATE = "DATE"
    TIMESTAMP = "TIMESTAMP"


class FilterOperator(StrEnum):
    EQ = "EQ"
    NE = "NE"
    GT = "GT"
    GTE = "GTE"
    LT = "LT"
    LTE = "LTE"
    IN = "IN"
    NOT_IN = "NOT_IN"
    BETWEEN = "BETWEEN"
    CONTAINS = "CONTAINS"
    STARTS_WITH = "STARTS_WITH"
    ENDS_WITH = "ENDS_WITH"
    IS_NULL = "IS_NULL"
    IS_NOT_NULL = "IS_NOT_NULL"


class AggregationFunction(StrEnum):
    COUNT = "COUNT"
    COUNT_DISTINCT = "COUNT_DISTINCT"
    SUM = "SUM"
    AVG = "AVG"
    MIN = "MIN"
    MAX = "MAX"


class SortDirection(StrEnum):
    ASC = "ASC"
    DESC = "DESC"


class LogicalOperator(StrEnum):
    AND = "AND"
    OR = "OR"


class TemporalGranularity(StrEnum):
    DAY = "DAY"
    WEEK = "WEEK"
    MONTH = "MONTH"
    QUARTER = "QUARTER"
    YEAR = "YEAR"


class AuthorizedColumn(ContractModel):
    column_name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$", max_length=160)
    business_name: str = Field(min_length=1, max_length=200)
    data_type: DataType


class AuthorizedSchema(ContractModel):
    entity_id: UUID
    columns: list[AuthorizedColumn] = Field(min_length=1, max_length=500)


class ReportPlanningRequest(ContractModel):
    schema_version: Literal["1.0"]
    request_id: UUID
    correlation_id: str = Field(min_length=1, max_length=100)
    actor_user_id: UUID
    capabilities: list[str] = Field(min_length=1, max_length=3)
    user_request: str = Field(min_length=1, max_length=4000)
    requested_language: str = Field(pattern=r"^[a-z]{2}(-[A-Z]{2})?$")
    authorized_schema: AuthorizedSchema


class OrderConstraints(ContractModel):
    max_preview_rows: int = Field(ge=1, le=100)
    timeout_seconds: int = Field(ge=1, le=1800)


class SelectItem(ContractModel):
    column: str
    alias: str | None = Field(default=None, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    display_label: str | None = Field(default=None, min_length=1, max_length=200)


class FilterItem(ContractModel):
    type: Literal["CONDITION"] = "CONDITION"
    column: str
    operator: FilterOperator
    value: Any | None = None
    values: list[Any] | None = Field(default=None, max_length=100)


class FilterGroup(ContractModel):
    type: Literal["GROUP"] = "GROUP"
    operator: LogicalOperator
    children: list["FilterExpression"] = Field(min_length=1, max_length=20)


FilterExpression = FilterItem | FilterGroup


class AggregationItem(ContractModel):
    function: AggregationFunction
    column: str | None = None
    alias: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    display_label: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def count_only_without_column(self) -> "AggregationItem":
        if self.column is None and self.function != AggregationFunction.COUNT:
            raise ValueError("only COUNT may omit column")
        return self


class OrderByItem(ContractModel):
    column: str
    direction: SortDirection


class TemporalGroupItem(ContractModel):
    column: str
    granularity: TemporalGranularity
    alias: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    display_label: str | None = Field(default=None, min_length=1, max_length=200)


class ChartHint(ContractModel):
    chart_type: Literal["TABLE", "BAR", "LINE", "PIE"]
    category_column: str | None = None
    value_column: str | None = None


class ReportPayload(ContractModel):
    select: list[SelectItem] = Field(min_length=1, max_length=100)
    # A list remains accepted as the v1 shorthand for an AND group.
    filters: list[FilterItem] | FilterExpression = Field(default_factory=list)
    group_by: list[str] = Field(default_factory=list, max_length=20)
    temporal_group_by: list[TemporalGroupItem] = Field(default_factory=list, max_length=20)
    aggregations: list[AggregationItem] = Field(default_factory=list, max_length=20)
    having: FilterExpression | None = None
    order_by: list[OrderByItem] = Field(default_factory=list, max_length=20)
    limit: int = Field(ge=1, le=10_000)
    chart_hints: list[ChartHint] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def bound_legacy_filter_list(self) -> "ReportPayload":
        if isinstance(self.filters, list) and len(self.filters) > 50:
            raise ValueError("filters may contain at most 50 conditions")
        return self


class ReportOrder(ContractModel):
    schema_version: Literal["1.0"]
    execution_type: Literal["REPORT"]
    entity_id: UUID
    requested_language: str = Field(pattern=r"^[a-z]{2}(-[A-Z]{2})?$")
    request_summary: str = Field(min_length=1, max_length=1000)
    constraints: OrderConstraints
    payload: ReportPayload


class ValidationIssue(ContractModel):
    code: str
    path: str
    message: str


class ReportPlanningResponse(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    request_id: UUID
    correlation_id: str
    provider: str
    model: str
    order: ReportOrder


class MlSplit(ContractModel):
    strategy: Literal["RANDOM"]
    training_ratio: float = Field(ge=0.6, le=0.9)
    seed: int = Field(ge=0, le=2_147_483_647)


class MlOutput(ContractModel):
    include_feature_importance: bool = True
    include_predictions_preview: bool = True


class MlCandidate(ContractModel):
    algorithm: Literal[
        "LINEAR_REGRESSION",
        "LOGISTIC_REGRESSION",
        "DECISION_TREE_REGRESSOR",
        "DECISION_TREE_CLASSIFIER",
        "RANDOM_FOREST_REGRESSOR",
        "RANDOM_FOREST_CLASSIFIER",
        "GBT_REGRESSOR",
        "GBT_CLASSIFIER",
        "XGBOOST_REGRESSOR",
        "XGBOOST_CLASSIFIER",
    ]
    parameter_grid: dict[str, list[Any]] = Field(default_factory=dict)


class MlSelection(ContractModel):
    strategy: Literal["TRAIN_VALIDATION_SPLIT"]
    primary_metric: Literal[
        "RMSE", "MAE", "R2", "ACCURACY", "F1", "PRECISION", "RECALL", "AUC",
    ]
    maximum_trials: int = Field(ge=1, le=50)
    training_ratio: float = Field(ge=0.5, le=0.85)
    validation_ratio: float = Field(ge=0.1, le=0.3)
    test_ratio: float = Field(ge=0.1, le=0.3)
    seed: int = Field(ge=0, le=2_147_483_647)

    @model_validator(mode="after")
    def ratios_total_one(self) -> "MlSelection":
        total = self.training_ratio + self.validation_ratio + self.test_ratio
        if abs(total - 1.0) > 0.000001:
            raise ValueError("training, validation, and test ratios must total 1.0")
        return self


class MlWhatIfChange(ContractModel):
    column: str = Field(min_length=1, max_length=100)
    percent_change: float = Field(ge=-25, le=25)

    @model_validator(mode="after")
    def change_must_not_be_zero(self) -> "MlWhatIfChange":
        if abs(self.percent_change) < 0.000001:
            raise ValueError("percentChange must not be zero")
        return self


class MlWhatIfScenario(ContractModel):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,49}$")
    changes: list[MlWhatIfChange] = Field(min_length=1, max_length=3)


class MlWhatIfAnalysis(ContractModel):
    objective: Literal["MAXIMIZE_TARGET", "MINIMIZE_TARGET"]
    scenarios: list[MlWhatIfScenario] = Field(min_length=1, max_length=6)


class MlPayload(ContractModel):
    problem_type: Literal["REGRESSION", "BINARY_CLASSIFICATION"]
    algorithm: Literal[
        "LINEAR_REGRESSION",
        "LOGISTIC_REGRESSION",
        "DECISION_TREE_REGRESSOR",
        "DECISION_TREE_CLASSIFIER",
        "RANDOM_FOREST_REGRESSOR",
        "RANDOM_FOREST_CLASSIFIER",
        "GBT_REGRESSOR",
        "GBT_CLASSIFIER",
        "XGBOOST_REGRESSOR",
        "XGBOOST_CLASSIFIER",
    ]
    target_column: str
    feature_columns: list[str] = Field(min_length=1, max_length=50)
    categorical_feature_columns: list[str] = Field(default_factory=list, max_length=50)
    filters: list[FilterItem] = Field(default_factory=list, max_length=20)
    split: MlSplit
    parameters: dict[str, Any] = Field(default_factory=dict)
    candidate_algorithms: list[MlCandidate] = Field(default_factory=list, max_length=5)
    selection: MlSelection | None = None
    what_if_analysis: MlWhatIfAnalysis | None = None
    metrics: list[Literal[
        "RMSE", "MAE", "R2", "ACCURACY", "F1", "PRECISION", "RECALL", "AUC",
    ]] = Field(
        min_length=1, max_length=6)
    output: MlOutput

    @model_validator(mode="after")
    def candidates_require_selection(self) -> "MlPayload":
        if bool(self.candidate_algorithms) != (self.selection is not None):
            raise ValueError("candidateAlgorithms and selection must be supplied together")
        return self


class MlOrder(ContractModel):
    schema_version: Literal["1.0"]
    execution_type: Literal["ML"]
    entity_id: UUID
    requested_language: str = Field(pattern=r"^[a-z]{2}(-[A-Z]{2})?$")
    request_summary: str = Field(min_length=1, max_length=1000)
    constraints: OrderConstraints
    payload: MlPayload


class MlPlanningResponse(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    request_id: UUID
    correlation_id: str
    provider: str
    model: str
    order: MlOrder
