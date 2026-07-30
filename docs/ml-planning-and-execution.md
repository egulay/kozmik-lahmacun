# Governed ML planning and execution

The explicit registry supports:

- regression with linear, decision-tree, random-forest, GBT, and XGBoost;
- binary classification with logistic, decision-tree, random-forest, GBT, and XGBoost.

Each algorithm has a bounded parameter registry. Regression metrics are RMSE,
MAE, and R2; classification metrics include accuracy, F1, precision, recall, and
AUC. Splits require an explicit deterministic seed. Automatic selection is
bounded to five algorithms and fifty trials.

ML suitability is derived from registered data types rather than stored
eligibility switches. Numeric columns may be targets; numeric and categorical
text columns may be features. Reporter requests are rejected by Java before
planning and independently rejected by Python validation.

The trusted executor constructs a fixed Spark `VectorAssembler` plus registered estimator
pipeline. It writes bounded prediction previews to the result contract, full predictions as
Parquet in `results`, and the Spark model as a ZIP artifact in `models`. No generated Python,
SQL, estimator class, pipeline stage, parameter name, or object path is executed from the order.
