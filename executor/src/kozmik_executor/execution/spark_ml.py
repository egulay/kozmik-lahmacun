import asyncio
import itertools
import math
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from minio import Minio
from pyspark.ml import Pipeline
from pyspark.ml.classification import (
    DecisionTreeClassifier,
    GBTClassifier,
    LogisticRegression,
    RandomForestClassifier,
)
from pyspark.ml.evaluation import (
    BinaryClassificationEvaluator,
    MulticlassClassificationEvaluator,
    RegressionEvaluator,
)
from pyspark.ml.feature import OneHotEncoder, StringIndexer, VectorAssembler
from pyspark.ml.functions import vector_to_array
from pyspark.ml.regression import (
    DecisionTreeRegressor,
    GBTRegressor,
    LinearRegression,
    RandomForestRegressor,
)
from pyspark.sql import functions as spark_fn

from kozmik_executor.planning.models import MlOrder
from kozmik_executor.execution.spark_report import FILTER_REGISTRY
from kozmik_executor.spark_runtime import run_spark_operation
from kozmik_executor.spark_session import build_spark_session

ML_NAMESPACE = UUID("8a859a44-9b33-49da-afbb-c6af731c9518")


class SparkMlExecutor:
    def __init__(self, spark=None, minio=None) -> None:
        self.spark = spark or build_spark_session("kozmik-ml-worker")
        self.minio = minio or Minio(
            os.getenv("MINIO_ENDPOINT", "localhost:9000"),
            access_key=os.getenv("MINIO_ACCESS_KEY", ""),
            secret_key=os.getenv("MINIO_SECRET_KEY", ""),
            secure=os.getenv("MINIO_SECURE", "false").lower() == "true")

    async def execute(
        self, execution_id: UUID, order: MlOrder, configuration: dict[str, Any],
        cancelled: asyncio.Event,
    ) -> dict[str, Any]:
        if cancelled.is_set():
            raise asyncio.CancelledError
        configuration = configuration.get("execution", configuration)
        timeout = min(order.constraints.timeout_seconds,
                      int(configuration.get("timeoutSeconds", order.constraints.timeout_seconds)))
        try:
            return await asyncio.wait_for(asyncio.to_thread(
                run_spark_operation, "ml-execution",
                self._execute, execution_id, order, configuration, cancelled), timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            cancelled.set()
            self.spark.sparkContext.cancelJobGroup(str(execution_id))
            raise

    def cancel(self, execution_id) -> None:
        self.spark.sparkContext.cancelJobGroup(str(execution_id))

    def _execute(self, execution_id, order, configuration, cancelled):
        uri = configuration.get("datasetUri")
        source_format = str(configuration.get("datasetFormat", "parquet")).lower()
        if not uri or source_format not in {"parquet", "json", "csv"}:
            raise ValueError("DATASET_CONFIGURATION_INVALID")
        reader = self.spark.read
        if source_format == "csv":
            reader = reader.option("header", True).option("inferSchema", True)
        data = reader.format(source_format).load(uri)
        for item in order.payload.filters:
            operation = FILTER_REGISTRY.get(item.operator)
            if operation is None:
                raise ValueError("FILTER_OPERATOR_NOT_ALLOWED")
            data = data.filter(operation(spark_fn.col(item.column), item))
        derivation = order.payload.binary_target_derivation
        if derivation is not None:
            source = spark_fn.col(derivation.source_column)
            comparisons = {
                "GT": source > derivation.threshold,
                "GTE": source >= derivation.threshold,
                "LT": source < derivation.threshold,
                "LTE": source <= derivation.threshold,
            }
            data = data.withColumn(
                order.payload.target_column,
                spark_fn.when(source.isNull(), spark_fn.lit(None).cast("double"))
                .when(comparisons[derivation.operator], spark_fn.lit(1.0))
                .otherwise(spark_fn.lit(0.0)),
            )
        data = data.select(
            *order.payload.feature_columns, order.payload.target_column).dropna()
        if order.payload.problem_type == "BINARY_CLASSIFICATION":
            labels = {
                float(row[0])
                for row in data.select(order.payload.target_column).distinct().limit(3).collect()
            }
            if not labels or not labels.issubset({0.0, 1.0}):
                raise ValueError("ML_BINARY_TARGET_INVALID")
        categorical = set(order.payload.categorical_feature_columns)
        encoded_columns = {
            name: f"__kozmik_encoded_{index}"
            for index, name in enumerate(order.payload.feature_columns)
            if name in categorical
        }
        feature_stages = []
        for name, encoded_name in encoded_columns.items():
            indexed_name = f"{encoded_name}_index"
            feature_stages.extend([
                StringIndexer(
                    inputCol=name, outputCol=indexed_name, handleInvalid="keep"),
                OneHotEncoder(
                    inputCols=[indexed_name], outputCols=[encoded_name],
                    handleInvalid="keep"),
            ])
        assembler = VectorAssembler(
            inputCols=[
                encoded_columns.get(name, name)
                for name in order.payload.feature_columns
            ],
            outputCol="features",
            handleInvalid="keep",
        )
        self.spark.sparkContext.setJobGroup(str(execution_id), "Kozmik governed ML", True)
        model, test, selection_facts = self._select_model(
            order, data, [*feature_stages, assembler], cancelled)
        if cancelled.is_set():
            raise asyncio.CancelledError
        predictions = model.transform(test)
        metrics = self._metrics(order, predictions)
        preview_limit = order.constraints.max_preview_rows
        preview_columns = [
            *order.payload.feature_columns, order.payload.target_column, "prediction",
        ]
        if order.payload.problem_type == "BINARY_CLASSIFICATION":
            predictions = predictions.withColumn(
                "positiveProbability", vector_to_array("probability")[1])
            preview_columns.append("positiveProbability")
        preview_frame = predictions.select(*preview_columns)
        row_count = preview_frame.count()
        rows = [row.asDict(recursive=True) for row in preview_frame.limit(preview_limit).collect()]
        importance = (
            self._importance(
                self._feature_names(
                    predictions,
                    order.payload.feature_columns,
                    encoded_columns,
                ),
                model.stages[-1],
            )
            if order.payload.output.include_feature_importance
            else []
        )
        scenario_chart = self._what_if_analysis(order, model, test, predictions)
        artifact_id = uuid5(ML_NAMESPACE, f"{execution_id}:predictions")
        model_id = uuid5(ML_NAMESPACE, f"{execution_id}:model")
        with tempfile.TemporaryDirectory(prefix="kozmik-ml-") as directory:
            predictions_path = Path(directory) / "predictions"
            preview_frame.coalesce(1).write.mode("overwrite").parquet(str(predictions_path))
            prediction_part = next(predictions_path.glob("part-*.parquet"))
            prediction_key = f"executions/{execution_id}/{artifact_id}.parquet"
            self.minio.fput_object("results", prediction_key, str(prediction_part))
            model_path = Path(directory) / "model"
            model.write().overwrite().save(str(model_path))
            archive = shutil.make_archive(str(Path(directory) / "model"), "zip", model_path)
            model_key = f"executions/{execution_id}/{model_id}.zip"
            self.minio.fput_object("models", model_key, archive)
            prediction_size = prediction_part.stat().st_size
            model_size = Path(archive).stat().st_size
        kpis = [{"code": name, "labelKey": f"result.metric.{name.lower()}",
                 "value": value, "unit": None} for name, value in metrics.items()]
        kpis.extend(selection_facts)
        if order.payload.problem_type == "BINARY_CLASSIFICATION":
            kpis.extend(self._classification_facts(predictions, order.payload.target_column))
        return {
            "rowCount": row_count,
            "preview": {"columns": [
                {"name": name, "type": "NUMBER"}
                for name in preview_columns],
                "rows": rows, "limit": preview_limit, "truncated": row_count > preview_limit},
            "kpis": kpis,
            "charts": ([{"chartId": "feature-importance", "type": "BAR",
                         "titleKey": "result.chart.featureImportance",
                         "categoryField": "feature",
                         "categories": [item["feature"] for item in importance],
                         "series": [{"name": "importance",
                                     "data": [item["importance"] for item in importance]}]}]
                       if importance else []) + ([scenario_chart] if scenario_chart else []),
            "warnings": (
                [{"code": "WHAT_IF_NOT_CAUSAL",
                  "messageKey": "result.warning.whatIfNotCausal"}]
                if scenario_chart else []
            ),
            "artifact": {"artifactId": str(artifact_id), "format": "PARQUET",
                         "bucket": "results", "objectKey": prediction_key,
                         "sizeBytes": prediction_size},
            "modelArtifact": {"artifactId": str(model_id), "format": "SPARK_ML_ZIP",
                              "bucket": "models", "objectKey": model_key,
                              "sizeBytes": model_size},
        }

    @staticmethod
    def _what_if_analysis(order, model, test, baseline_predictions):
        analysis = order.payload.what_if_analysis
        if analysis is None:
            return None
        baseline = baseline_predictions.agg(
            spark_fn.avg("prediction").alias("value")).first()["value"]
        if baseline is None:
            raise ValueError("ML_WHAT_IF_BASELINE_EMPTY")
        scenario_facts = []
        deltas = []
        for scenario in analysis.scenarios:
            scenario_data = test
            changes = []
            for change in scenario.changes:
                scenario_data = scenario_data.withColumn(
                    change.column,
                    spark_fn.col(change.column) * (1.0 + change.percent_change / 100.0),
                )
                changes.append({
                    "column": change.column,
                    "percentChange": float(change.percent_change),
                })
            scenario_value = model.transform(scenario_data).agg(
                spark_fn.avg("prediction").alias("value")).first()["value"]
            if scenario_value is None:
                raise ValueError("ML_WHAT_IF_SCENARIO_EMPTY")
            delta = float(scenario_value) - float(baseline)
            delta_percent = (
                delta / abs(float(baseline)) * 100.0
                if abs(float(baseline)) > 0.000000001 else 0.0
            )
            deltas.append(delta_percent)
            scenario_facts.append({
                "code": scenario.code,
                "changes": changes,
                "baselinePrediction": float(baseline),
                "scenarioPrediction": float(scenario_value),
                "delta": delta,
                "deltaPercent": delta_percent,
            })
        return {
            "chartId": "what-if-analysis",
            "type": "BAR",
            "titleKey": "result.chart.whatIfAnalysis",
            "categoryField": "scenario",
            "categories": [item.code for item in analysis.scenarios],
            "series": [{"name": "predictedChangePercent", "data": deltas}],
            "objective": analysis.objective,
            "scenarioFacts": scenario_facts,
        }

    def _select_model(self, order, data, feature_stages, cancelled):
        selection = order.payload.selection
        if not order.payload.candidate_algorithms or selection is None:
            training, test = data.randomSplit(
                [order.payload.split.training_ratio, 1 - order.payload.split.training_ratio],
                seed=order.payload.split.seed)
            self._require_nonempty(training, test)
            model = Pipeline(stages=[*feature_stages, self._estimator(order)]).fit(training)
            return model, test, []

        training, validation, test = data.randomSplit(
            [
                selection.training_ratio,
                selection.validation_ratio,
                selection.test_ratio,
            ],
            seed=selection.seed,
        )
        self._require_nonempty(training, validation, test)
        best = None
        trials = []
        for candidate in order.payload.candidate_algorithms:
            names = sorted(candidate.parameter_grid)
            combinations = (
                itertools.product(*(candidate.parameter_grid[name] for name in names))
                if names else [()]
            )
            for combination in combinations:
                if cancelled.is_set():
                    raise asyncio.CancelledError
                parameters = dict(zip(names, combination, strict=True))
                estimator = self._estimator(
                    order, candidate.algorithm, parameters, selection.seed)
                model = Pipeline(stages=[*feature_stages, estimator]).fit(training)
                score = self._metric(
                    order, model.transform(validation), selection.primary_metric)
                trial = {
                    "algorithm": candidate.algorithm,
                    "parameters": parameters,
                    "score": float(score),
                }
                trials.append(trial)
                if best is None or self._better(
                    score, best["score"], selection.primary_metric
                ):
                    best = trial
        if best is None:
            raise ValueError("ML_MODEL_SELECTION_FAILED")
        final_training = training.unionByName(validation)
        final_estimator = self._estimator(
            order, best["algorithm"], best["parameters"], selection.seed)
        final_model = Pipeline(
            stages=[*feature_stages, final_estimator]
        ).fit(final_training)
        return final_model, test, [
            {
                "code": "SELECTED_ALGORITHM",
                "labelKey": "result.metric.selectedAlgorithm",
                "value": best["algorithm"],
                "unit": None,
            },
            {
                "code": "BEST_VALIDATION_SCORE",
                "labelKey": "result.metric.bestValidationScore",
                "value": float(best["score"]),
                "unit": selection.primary_metric,
            },
            {
                "code": "TUNING_TRIALS_EVALUATED",
                "labelKey": "result.metric.tuningTrialsEvaluated",
                "value": len(trials),
                "unit": None,
            },
            {
                "code": "CANDIDATE_ALGORITHMS_EVALUATED",
                "labelKey": "result.metric.candidateAlgorithmsEvaluated",
                "value": len(order.payload.candidate_algorithms),
                "unit": None,
            },
        ]

    @staticmethod
    def _require_nonempty(*frames):
        if any(frame.limit(1).count() == 0 for frame in frames):
            raise ValueError("ML_SPLIT_EMPTY")

    @staticmethod
    def _better(candidate, current, metric):
        return candidate < current if metric in {"RMSE", "MAE"} else candidate > current

    @staticmethod
    def _estimator(order, algorithm=None, parameters=None, seed=None):
        label = order.payload.target_column
        algorithm = algorithm or order.payload.algorithm
        values = parameters if parameters is not None else order.payload.parameters
        seed = order.payload.split.seed if seed is None else seed
        common_tree = {
            "featuresCol": "features",
            "labelCol": label,
            "maxDepth": int(values.get("maxDepth", 5)),
            "minInstancesPerNode": int(values.get("minInstancesPerNode", 1)),
            "minInfoGain": float(values.get("minInfoGain", 0.0)),
        }
        forest = {
            **common_tree,
            "numTrees": int(values.get("numTrees", 100)),
            "featureSubsetStrategy": str(values.get("featureSubsetStrategy", "auto")),
            "subsamplingRate": float(values.get("subsamplingRate", 1.0)),
            "seed": int(values.get("seed", seed)),
        }
        boosted = {
            **common_tree,
            "maxIter": int(values.get("maxIter", 100)),
            "stepSize": float(values.get("stepSize", 0.1)),
            "subsamplingRate": float(values.get("subsamplingRate", 1.0)),
            "seed": int(values.get("seed", seed)),
        }
        builders = {
            "LINEAR_REGRESSION": lambda: LinearRegression(
                featuresCol="features", labelCol=label,
                maxIter=int(values.get("maxIter", 100)),
                regParam=float(values.get("regParam", 0.0))),
            "LOGISTIC_REGRESSION": lambda: LogisticRegression(
                featuresCol="features", labelCol=label,
                maxIter=int(values.get("maxIter", 100)),
                regParam=float(values.get("regParam", 0.0))),
            "DECISION_TREE_REGRESSOR": lambda: DecisionTreeRegressor(**common_tree),
            "DECISION_TREE_CLASSIFIER": lambda: DecisionTreeClassifier(**common_tree),
            "RANDOM_FOREST_REGRESSOR": lambda: RandomForestRegressor(**forest),
            "RANDOM_FOREST_CLASSIFIER": lambda: RandomForestClassifier(**forest),
            "GBT_REGRESSOR": lambda: GBTRegressor(**boosted),
            "GBT_CLASSIFIER": lambda: GBTClassifier(**boosted),
            "XGBOOST_REGRESSOR": lambda: SparkMlExecutor._xgboost(
                False, label, values, seed),
            "XGBOOST_CLASSIFIER": lambda: SparkMlExecutor._xgboost(
                True, label, values, seed),
        }
        builder = builders.get(algorithm)
        if builder is None:
            raise ValueError("ALGORITHM_NOT_ALLOWED")
        return builder()

    @staticmethod
    def _xgboost(classifier, label, values, default_seed):
        try:
            from xgboost.spark import SparkXGBClassifier, SparkXGBRegressor
        except ImportError as exception:
            raise ValueError("XGBOOST_RUNTIME_UNAVAILABLE") from exception
        constructor = SparkXGBClassifier if classifier else SparkXGBRegressor
        return constructor(
            features_col="features",
            label_col=label,
            num_workers=1,
            max_depth=int(values.get("maxDepth", 6)),
            n_estimators=int(values.get("numRounds", 100)),
            learning_rate=float(values.get("learningRate", 0.1)),
            min_child_weight=float(values.get("minChildWeight", 1.0)),
            subsample=float(values.get("subsample", 1.0)),
            colsample_bytree=float(values.get("colsampleBytree", 1.0)),
            reg_alpha=float(values.get("regAlpha", 0.0)),
            reg_lambda=float(values.get("regLambda", 1.0)),
            random_state=int(values.get("seed", default_seed)),
        )

    @staticmethod
    def _metrics(order, predictions):
        return {
            metric: SparkMlExecutor._evaluate_metric(
                order.payload.target_column, predictions, metric)
            for metric in order.payload.metrics
        }

    @staticmethod
    def _metric(order, predictions, metric):
        return SparkMlExecutor._evaluate_metric(
            order.payload.target_column, predictions, metric)

    @staticmethod
    def _evaluate_metric(target_column, predictions, metric):
        if metric in {"RMSE", "MAE", "R2"}:
            names = {"RMSE": "rmse", "MAE": "mae", "R2": "r2"}
            evaluator = RegressionEvaluator(
                labelCol=target_column, metricName=names[metric])
        elif metric == "AUC":
            evaluator = BinaryClassificationEvaluator(
                labelCol=target_column, metricName="areaUnderROC")
        else:
            names = {
                "ACCURACY": "accuracy",
                "F1": "f1",
                "PRECISION": "weightedPrecision",
                "RECALL": "weightedRecall",
            }
            evaluator = MulticlassClassificationEvaluator(
                labelCol=target_column, metricName=names[metric])
        return evaluator.evaluate(predictions)

    @staticmethod
    def _importance(feature_names, estimator_model):
        if hasattr(estimator_model, "featureImportances"):
            values = estimator_model.featureImportances.toArray().tolist()
        elif hasattr(estimator_model, "coefficients"):
            values = estimator_model.coefficients.toArray().tolist()
        elif hasattr(estimator_model, "get_feature_importances"):
            importance = estimator_model.get_feature_importances()
            values = [float(importance.get(f"f{index}", 0.0))
                      for index in range(len(feature_names))]
        else:
            return []
        if len(feature_names) != len(values):
            feature_names = [f"feature_{index + 1}" for index in range(len(values))]
        return [{"feature": name, "importance": abs(float(value))}
                for name, value in zip(feature_names, values, strict=True)
                if not math.isclose(float(value), 0.0, abs_tol=1e-12)]

    @staticmethod
    def _feature_names(predictions, fallback, encoded_columns=None):
        metadata = predictions.schema["features"].metadata.get("ml_attr", {})
        attrs = metadata.get("attrs", {})
        indexed = [
            item for group in attrs.values() for item in group
            if "idx" in item and "name" in item
        ]
        if not indexed:
            return list(fallback)
        encoded_to_source = {
            encoded: source
            for source, encoded in (encoded_columns or {}).items()
        }

        def display_name(name):
            for encoded, source in encoded_to_source.items():
                prefix = f"{encoded}_"
                if name.startswith(prefix):
                    category = name.removeprefix(prefix)
                    if category == "__unknown":
                        category = "unknown"
                    return f"{source}: {category}"
            return name

        return [
            display_name(item["name"])
            for item in sorted(indexed, key=lambda item: item["idx"])
        ]

    @staticmethod
    def _classification_facts(predictions, target_column):
        total = predictions.count()
        if total == 0:
            return []
        aggregated = predictions.agg(
            spark_fn.avg("positiveProbability").alias("average_probability"),
            spark_fn.avg(
                spark_fn.when(spark_fn.col("positiveProbability") >= 0.5, 1.0)
                .otherwise(0.0)
            ).alias("positive_rate"),
            spark_fn.avg(
                spark_fn.when(spark_fn.col("prediction") == spark_fn.col(target_column), 1.0)
                .otherwise(0.0)
            ).alias("correct_rate"),
        ).first()
        return [
            {"code": "AVERAGE_POSITIVE_PROBABILITY",
             "labelKey": "result.metric.averagePositiveProbability",
             "value": float(aggregated["average_probability"]) * 100, "unit": "PERCENT"},
            {"code": "PREDICTED_POSITIVE_RATE",
             "labelKey": "result.metric.predictedPositiveRate",
             "value": float(aggregated["positive_rate"]) * 100, "unit": "PERCENT"},
            {"code": "CORRECT_PREDICTION_RATE",
             "labelKey": "result.metric.correctPredictionRate",
             "value": float(aggregated["correct_rate"]) * 100, "unit": "PERCENT"},
        ]
