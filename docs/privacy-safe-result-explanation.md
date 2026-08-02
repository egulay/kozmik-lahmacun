# Privacy-safe management-summary pipeline

Management explanation is a non-critical final stage after Spark completes the analytical work
and writes durable artifacts. Summary failure never changes a successful report or ML execution
into a failed analytical result.

## Pipeline

```text
Spark result
  -> privacy-safe calculated result JSON (ManagementEvidence 2.0)
  -> original request + calculated result JSON
  -> LLM prose-only response
  -> natural-prose validation
  -> at most one evidence-only prose repair
  -> executor-owned ManagementSummaryAudit 2.0
  -> transactional result and summary-audit persistence
```

The LLM does not receive an unrestricted result payload. It receives the original request and the
complete privacy-safe calculated result JSON, and returns only prose. For grouped reports this JSON
contains every safe grouping value, requested aggregate, and calculated additive share in
`reportBreakdown`; it is not reduced to a second intermediate summary. For ML it contains approved
evaluation measurements, selection facts, model-reliance fields when available, and executed
scenario comparisons. The executor—not the provider—owns evidence IDs, combined evidence scope,
validation disposition, and audit structure.

## Semantic registry

`summary_semantics.py` is the central registry for supported report and ML meanings. Each entry
defines:

- canonical business meaning;
- permitted execution and problem types;
- valid evidence scopes;
- value and unit behavior;
- inherent mathematical directionality;
- permitted and forbidden interpretations;
- required context;
- comparison, recommendation, and business-direction permissions.

The registry distinguishes totals, counts, averages, extrema, absolute difference, symmetric
relative spread, share of total, time-based percentage change, normalized ratios, regression and
classification metrics, validation scores, test scores, feature importance, and scenario deltas.

Mathematical directionality is not automatically a management judgment. For example, a lower
error metric is preferred during model selection, but the resulting error cannot be called
acceptable without an approved business tolerance or comparison.

## Evidence and scope contracts

Python creates `ManagementEvidence` schema `2.0` with semantic-registry version `1.0`.
Every fact has a stable evidence ID and explicit scope.

Report evidence may include:

- complete privacy-safe grouped result breakdowns with all requested aggregate values;
- per-group shares calculated for additive count and sum measures;
- complete-result scalar aggregates;
- complete-result grouped extrema with grouping dimensions and endpoint values;
- grouped-extremum tie counts so a tied value cannot be presented as uniquely highest or lowest;
- absolute spread;
- symmetric relative spread, explicitly distinct from temporal change and share;
- separately calculated share of total;
- numerator-per-denominator comparisons;
- safely additive earlier-to-later time changes;
- bounded chart highlights explicitly marked `BOUNDED_CHART_DATA`.

Report measures remain context-dependent. A larger value is not automatically better, and the
governed display label must be preserved rather than replaced with a related business concept.

ML evidence may include:

- every approved input field and the governed prediction target;
- final metrics scoped to `UNTOUCHED_TEST_DATA`;
- validation-only model-selection facts scoped to `VALIDATION_DATA_ONLY`;
- class averaging scope where relevant;
- evaluated-case and majority-baseline context;
- selected-model tree-native feature importance with no direction or causality;
- executed scenario values and deltas scoped to `SCENARIO_COMPARISON`.

The complete approved ML outcome is supplied to the summary provider: input fields, target,
supported evaluation indicators and their business definitions, selected approach, candidate and
tuning counts, validation selection result, model-reliance values, executed scenarios, warnings,
and result cardinality. Source rows and prediction-preview rows are excluded because they do not
change the management explanation and may contain business records.

MAE is mean absolute prediction error. RMSE is the square root of mean squared error and gives
larger errors more influence. R2 represents captured variation. AUC represents ranking
separation. These meanings are not interchangeable with accuracy, confidence, probability,
reliability, or business acceptability.

Raw, unstandardized linear-model coefficients are not published as comparable feature importance.

## Executor-owned summary audit

The executor constructs `ManagementSummaryAudit` schema `2.0` containing:

- output language;
- the single provider-authored management prose accepted for publication;
- the complete set of evidence references supplied to that generation;
- the combined evidence and population scopes, grouping dimensions and endpoint values,
  periods, aggregations, evaluation roles, selected-model metadata, selection metrics, and
  scenario codes;
- schema version for durable contract validation.

There is no claim, conclusion, recommendation, priority, or intermediate-narrative object in the
active summary contract. The browser renders the validated prose directly. Its evidence references
and combined scope are retained for audit but are not exposed as browser management text.

## Narrative requirements

The prose must lead with the most material calculated pattern, support it with correctly scoped
facts, contrast material variation with comparative stability where evidence permits, and explain
practical decision-support use. It must not repeat the request, narrate execution mechanics,
enumerate every metric equally, or expose internal authorization and contract terminology.

No word, sentence, paragraph, character, or application token limit is imposed on the persisted
management summary or summary audit.

## Privacy boundary

Only allowlisted calculated result data is serialized for the provider. The evidence builder
excludes:

- report and prediction preview rows;
- artifact locations;
- direct identifier dimensions such as customer, subscriber, account, phone, email, UUID, and
  name fields;
- arbitrary KPI fields;
- warning details that the UI renders separately.

One-hot categories are combined into their governed source field before tree-native model-reliance
evidence is produced. A repair call receives the same business facts, the rejected prose, and
prose-validation issues; it never receives raw business records or executor-owned audit metadata.

## Validation and repair

Prose validation rejects:

- invented numbers, units, currencies, percentages, or business thresholds;
- unsupported causality, guarantees, direction, or recommendations;
- relative spread presented as growth, temporal change, share, improvement, or deterioration;
- RMSE presented as average magnitude or percentage;
- R2 or AUC presented as confidence, probability, reliability, or general accuracy;
- multiple unlike regression or classification metrics collectively labeled accuracy;
- feature importance presented as effect direction, causality, or contribution to accuracy;
- qualitative judgments such as strong, weak, reliable, acceptable, actionable, or
  production-ready without typed tolerance or acceptance evidence;
- output in a language other than requested English or Turkish.
- mixed English/Turkish narrative except governed labels that have no localized display label.

Weak synthesis, technical inventories, missing material findings, repeated warnings, and internal
policy language are advisory issues. Blocking issues trigger a prose-only repair. If a provider
still returns a mixture of safe and unsafe prose, the executor validates each provider-written
sentence, retains only independently safe sentences, recombines them, and validates the complete
result again. Provider-invented generic `unit`/`units`/`birim` wording immediately following an
approved unitless number can be removed deterministically before the same complete revalidation.
Neither recovery path creates facts, numbers, units, conclusions, or recommendations.

The summary is rejected only when no non-empty provider prose survives validation, the provider is
unavailable, or its response cannot be parsed. The analytical result remains usable in that state.
No hardcoded or deterministic fake management summary replaces rejected LLM text.

## Persistence and observability

The signed Kafka result event carries:

- unbounded `managementSummary` text when accepted;
- exact `summaryEvidence` and evidence schema version;
- executor-owned `summaryAudit` when available;
- validation disposition;
- combined, blocking, and advisory issue codes;
- repair-attempt count;
- non-secret provider and model identifiers;
- generation timestamp.

Java validates the disposition and transactionally persists these fields with the analytical
result. Structured logs record generation, validation, repair, acceptance, rejection, and provider
failure without logging evidence payloads, raw data, or full prompts.

Migration V24 marks pre-evidence summaries `LEGACY_UNVALIDATED`. Migration V25 added generation
audit persistence. Migration V26 renamed the audit column to reflect executor ownership. Migration
V27 converts the earlier claim-oriented JSON into the simplified schema `2.0` prose/evidence/scope
contract while retaining historical validation status.

## Deliberate limitations

- Natural-language validation is conservative. The service validates the final prose against typed
  calculated evidence, but this does not constitute a formal proof of every possible linguistic
  implication.
- No unit, currency, business threshold, or measure desirability is inferred when governed
  metadata does not provide it.
- Linear and logistic coefficient magnitudes are not ranked unless a future governed
  standardization method makes them comparable.
- Feature importance describes model reliance, not direction or causality.
- Recommendations require executed what-if scenarios and remain conditional model comparisons,
  not causal evidence.
- Safely additive time comparisons currently cover SUM and COUNT measures. Non-additive rollups
  require an explicitly governed weighting or aggregation contract.
- Chart highlights may be bounded; complete-result evidence is calculated and scoped separately.
- Provider or semantic rejection leaves the analytical result usable but without an accepted
  management summary.
