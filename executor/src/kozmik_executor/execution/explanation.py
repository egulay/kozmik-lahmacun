import json
import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import Field

from kozmik_executor.chat.models import ContractModel, EffectiveLlmConfiguration
from kozmik_executor.chat.providers import ProviderError, ProviderRegistry
from kozmik_executor.execution.models import ExecutionCommand

logger = logging.getLogger(__name__)


class ApprovedFact(ContractModel):
    code: str = Field(max_length=100)
    label_key: str | None = Field(default=None, max_length=200)
    value: int | float | str | bool | None = None
    unit: str | None = Field(default=None, max_length=40)


class ApprovedWarning(ContractModel):
    code: str = Field(max_length=100)
    message_key: str | None = Field(default=None, max_length=200)


class ApprovedDriver(ContractModel):
    feature: str = Field(max_length=100)
    importance: float = Field(ge=0)


class ApprovedScenarioChange(ContractModel):
    column: str = Field(max_length=100)
    percent_change: float = Field(ge=-25, le=25)


class ApprovedScenario(ContractModel):
    code: str = Field(max_length=50)
    changes: list[ApprovedScenarioChange] = Field(min_length=1, max_length=3)
    delta_percent: float


class ApprovedReportBreakdown(ContractModel):
    dimensions: dict[str, int | float | str | bool | None] = Field(max_length=20)
    measures: dict[str, int | float | str | bool | None] = Field(max_length=20)


class SummaryFacts(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    execution_type: Literal["REPORT", "ML"]
    language: Literal["tr", "en"]
    row_count: int = Field(ge=0)
    algorithm: str | None = Field(default=None, max_length=100)
    target: str | None = Field(default=None, max_length=100)
    features: list[str] = Field(default_factory=list, max_length=20)
    drivers: list[ApprovedDriver] = Field(default_factory=list, max_length=10)
    scenario_objective: Literal["MAXIMIZE_TARGET", "MINIMIZE_TARGET"] | None = None
    scenarios: list[ApprovedScenario] = Field(default_factory=list, max_length=6)
    report_breakdown: list[ApprovedReportBreakdown] = Field(
        default_factory=list, max_length=10)
    facts: list[ApprovedFact] = Field(max_length=20)
    warnings: list[ApprovedWarning] = Field(max_length=20)


class ExplanationOutcome(ContractModel):
    status: Literal["COMPLETED", "FAILED"]
    text: str | None = Field(default=None, max_length=4000)


class ResultExplainer:
    MAX_FACTS_JSON = 12_000

    def __init__(self, registry: ProviderRegistry | None = None) -> None:
        self.registry = registry or ProviderRegistry()

    def build_facts(self, command: ExecutionCommand, result: dict[str, Any]) -> SummaryFacts:
        language = "tr" if command.order.requested_language.lower().startswith("tr") else "en"
        approved_facts = [
            ApprovedFact.model_validate({
                "code": item.get("code"), "labelKey": item.get("labelKey"),
                "value": (
                    str(item.get("value"))
                    if isinstance(item.get("value"), Decimal)
                    else item.get("value")
                ),
                "unit": item.get("unit"),
            })
            for item in result.get("kpis", [])[:20]
            if isinstance(item, dict) and isinstance(item.get("code"), str)
            and isinstance(
                item.get("value"), (int, float, Decimal, str, bool, type(None)))
        ]
        selected_algorithm = next(
            (
                str(fact.value)
                for fact in approved_facts
                if fact.code == "SELECTED_ALGORITHM" and isinstance(fact.value, str)
            ),
            None,
        )
        algorithm = (
            selected_algorithm or command.order.payload.algorithm
            if command.execution_type == "ML"
            else None
        )
        warnings = [
            ApprovedWarning.model_validate({
                "code": item.get("code"), "messageKey": item.get("messageKey"),
            })
            for item in result.get("warnings", [])[:20]
            if isinstance(item, dict) and isinstance(item.get("code"), str)
        ]
        target = None
        features: list[str] = []
        if command.execution_type == "ML":
            target = command.order.payload.target_column
            features = list(command.order.payload.feature_columns[:20])
        drivers = self._approved_drivers(result)
        scenario_objective, scenarios = self._approved_scenarios(result)
        report_breakdown = self._approved_report_breakdown(command, result)
        facts = SummaryFacts(
            executionType=command.execution_type, language=language,
            rowCount=result["rowCount"], algorithm=algorithm,
            target=target, features=features, drivers=drivers,
            scenarioObjective=scenario_objective, scenarios=scenarios,
            reportBreakdown=report_breakdown,
            facts=approved_facts, warnings=warnings)
        encoded = facts.model_dump_json(by_alias=True)
        if len(encoded) > self.MAX_FACTS_JSON:
            raise ValueError("SUMMARY_FACTS_LIMIT_EXCEEDED")
        return facts

    async def explain(
        self, command: ExecutionCommand, result: dict[str, Any],
    ) -> ExplanationOutcome:
        try:
            facts = self.build_facts(command, result)
            llm = EffectiveLlmConfiguration.model_validate(command.configuration["llm"])
            provider = self.registry.resolve(llm)
            language_instruction = (
                "Write the entire response in concise management-oriented Turkish. "
                "Do not include an English closing sentence or repeat an instruction phrase "
                "in English."
                if facts.language == "tr"
                else "Write the entire response in concise management-oriented English."
            )
            conditional_recommendation_instruction = (
                "Onaylı senaryo bulguları bir eylemi doğrudan destekliyorsa, "
                "\"Test edilen varsayımlar altında\" ifadesiyle başlayan, koşullu ve tamamen "
                "Türkçe tek bir öneri ekle. "
                if facts.language == "tr"
                else
                "When approved scenario facts directly support an action, add one clearly "
                "conditional recommendation beginning with 'Under the tested assumptions'. "
            )
            execution_instruction = (
                "For a REPORT, approved facts and reportBreakdown are calculated aggregate "
                "business results. Use their values to describe the main comparison, range, "
                "ranking, or time pattern in plain language. You may state these approved "
                "aggregate values. reportBreakdown contains bounded grouped aggregates, not raw "
                "source rows. Never claim that governed facts are absent when facts or "
                "reportBreakdown is non-empty. Summarize the requested comparison without adding "
                "a directional recommendation or generic what-if discussion. "
                if facts.execution_type == "REPORT"
                else
                "For ML, do not repeat raw metric values, algorithm names, row counts, tuning "
                "trials, or split details; those are shown elsewhere. Describe reliability "
                "qualitatively and conservatively. Do not recommend increasing, decreasing, "
                "raising, reducing, changing, adjusting, maintaining, expanding, or limiting "
                "any business input unless approved scenario facts directly establish it. "
                + conditional_recommendation_instruction +
                "When they do not, say that the result does not establish an increase/decrease "
                "action and name the controlled what-if analysis needed for such a decision. "
            )
            messages = [
                {"role": "system", "content": (
                    "Write a plain-language decision summary for a non-technical manager using "
                    "only the supplied governed aggregate facts. Lead with what the result means "
                    "and how it may be used in a business decision. Mention the strongest approved "
                    "drivers when supplied. Approved warnings are rendered in a separate UI "
                    "section: do not repeat, paraphrase, or expand them in the summary. Do not "
                    "invent assumptions about competitors, market stability, demand shifts, "
                    "costs, profit, or customer behavior. "
                    + execution_instruction +
                    "Never convert R2, "
                    "accuracy, RMSE, or MAE into a probability or confidence percentage. State a "
                    "probability only when an approved probability fact is explicitly supplied. "
                    "Do not claim a forecast, causal effect, or guaranteed outcome unless "
                    "approved scenario facts directly establish it. "
                    "Write one short paragraph of at most 80 words. "
                    "Return only the paragraph text. Do not add headings, labels, Markdown, "
                    "'Decision Summary', 'Approved Warnings', or a warnings section. "
                    "Do not infer identifiers, people, customers, raw rows, or unsupported causes. "
                    + language_instruction)},
                {"role": "user", "content": json.dumps(
                    facts.model_dump(by_alias=True, mode="json"),
                    separators=(",", ":"), ensure_ascii=False)},
            ]
            text = self._clean_management_summary(
                await self._complete(provider, messages)
            )
            if not text:
                raise ProviderError("LLM_SUMMARY_EMPTY")
            violations = self._management_violations(text)
            violations.extend(self._grounding_violations(text, facts))
            violations.extend(self._warning_duplication_violations(text, facts))
            if violations:
                repair_messages = [
                    *messages,
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": (
                        "Rewrite the summary. It violated these output rules: "
                        f"{', '.join(violations)}. Discuss business meaning only. Do not add "
                        "facts, uses, recommendations, probabilities, or forecasts.")},
                ]
                text = self._clean_management_summary(
                    await self._complete(provider, repair_messages)
                )
            remaining_violations = (
                self._management_violations(text)
                + self._grounding_violations(text, facts)
                + self._warning_duplication_violations(text, facts)
                if text else ["empty management summary"]
            )
            if remaining_violations:
                logger.info(
                    "result_explanation_repair_required executionType=%s violations=%s",
                    facts.execution_type,
                    ",".join(sorted(set(remaining_violations))),
                )
                grounded_draft = self._grounded_management_fallback(facts)
                guided_messages = [
                    *messages,
                    {"role": "user", "content": (
                        "The previous responses could not be accepted. Rewrite the supplied "
                        "fact-grounded draft as the final management summary. Preserve its "
                        "calculated facts and limitations exactly, but make the wording natural "
                        "and non-technical. Do not mention this instruction, a draft, validation, "
                        "or implementation details.\n\nFact-grounded draft:\n"
                        f"{grounded_draft}")},
                ]
                text = self._clean_management_summary(
                    await self._complete(provider, guided_messages)
                )
            final_violations = (
                self._management_violations(text)
                + self._grounding_violations(text, facts)
                + self._warning_duplication_violations(text, facts)
                if text else ["empty management summary"]
            )
            if final_violations:
                logger.warning(
                    "result_explanation_rejected code=SUMMARY_OUTPUT_INVALID "
                    "executionType=%s violations=%s",
                    facts.execution_type,
                    ",".join(sorted(set(final_violations))),
                )
                return ExplanationOutcome(status="FAILED")
            return ExplanationOutcome(status="COMPLETED", text=text)
        except (ProviderError, ValueError, KeyError) as exception:
            logger.warning(
                "result_explanation_failed code=SUMMARY_GENERATION_FAILED "
                "exceptionType=%s",
                type(exception).__name__,
            )
            return ExplanationOutcome(status="FAILED")

    @staticmethod
    def _clean_management_summary(text: str) -> str:
        """Remove provider-added presentation labels from manager-facing prose."""
        cleaned = re.sub(
            r"^\s*(?:\*\*)?(?:decision summary|management summary|"
            r"karar özeti|yönetici özeti)(?:\*\*)?\s*:?\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )
        cleaned = re.split(
            r"\s*(?:\*\*)?(?:approved warnings|onaylı uyarılar)"
            r"(?:\*\*)?\s*:?\s*",
            cleaned,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        return cleaned.replace("**", "").replace("__", "").strip()

    @staticmethod
    def _approved_drivers(result: dict[str, Any]) -> list[ApprovedDriver]:
        for chart in result.get("charts", [])[:10]:
            if not isinstance(chart, dict) or chart.get("chartId") != "feature-importance":
                continue
            categories = chart.get("categories")
            series = chart.get("series")
            if (
                not isinstance(categories, list)
                or not isinstance(series, list)
                or not series
                or not isinstance(series[0], dict)
                or not isinstance(series[0].get("data"), list)
            ):
                return []
            drivers = [
                ApprovedDriver(feature=feature, importance=float(importance))
                for feature, importance in zip(
                    categories[:10], series[0]["data"][:10], strict=False)
                if isinstance(feature, str)
                and isinstance(importance, (int, float))
                and not isinstance(importance, bool)
                and importance >= 0
            ]
            return sorted(drivers, key=lambda item: item.importance, reverse=True)
        return []

    @staticmethod
    def _approved_scenarios(
        result: dict[str, Any],
    ) -> tuple[str | None, list[ApprovedScenario]]:
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
                    ApprovedScenarioChange.model_validate(change)
                    for change in item.get("changes", [])[:3]
                    if isinstance(change, dict)
                ]
                delta = item.get("deltaPercent")
                if changes and isinstance(delta, (int, float)) and not isinstance(delta, bool):
                    approved.append(ApprovedScenario(
                        code=item["code"], changes=changes, deltaPercent=float(delta)))
            return objective, approved
        return None, []

    @staticmethod
    def _approved_report_breakdown(
        command: ExecutionCommand, result: dict[str, Any],
    ) -> list[ApprovedReportBreakdown]:
        if command.execution_type != "REPORT" or not command.order.payload.aggregations:
            return []
        temporal_aliases = {
            item.alias for item in command.order.payload.temporal_group_by
        }
        dimension_aliases = [
            item.alias or item.column
            for item in command.order.payload.select
            if item.column in command.order.payload.group_by
            or (item.alias or item.column) in temporal_aliases
        ]
        measure_aliases = [
            item.alias for item in command.order.payload.aggregations
        ]
        preview = result.get("preview")
        rows = preview.get("rows") if isinstance(preview, dict) else None
        if not isinstance(rows, list):
            return []

        def approved(values: dict[str, Any], names: list[str]) -> dict[str, Any]:
            return {
                name: (
                    str(values[name])
                    if isinstance(values[name], Decimal)
                    else values[name]
                )
                for name in names
                if name in values
                and isinstance(
                    values[name], (int, float, Decimal, str, bool, type(None)))
            }

        return [
            ApprovedReportBreakdown(
                dimensions=approved(row, dimension_aliases),
                measures=approved(row, measure_aliases),
            )
            for row in rows[:10]
            if isinstance(row, dict)
        ]

    @staticmethod
    async def _complete(provider, messages: list[dict[str, str]]) -> str:
        chunks = []
        length = 0
        async for chunk in provider.stream(messages):
            length += len(chunk)
            if length > 4000:
                raise ProviderError("LLM_SUMMARY_TOO_LARGE")
            chunks.append(chunk)
        return "".join(chunks).strip()

    @staticmethod
    def _management_violations(text: str) -> list[str]:
        violations = []
        if len(text.split()) > 100:
            violations.append("maximum 100 words")
        technical = re.compile(
            r"\b(?:regressor|classifier|hyperparameters?|tuning trials?|"
            r"training split|validation split|test[- ]set|r2|rmse|mae|gbt|xgboost|"
            r"random forest|decision tree|linear regression|"
            r"governed facts?|reportbreakdown)\b|r²",
            re.IGNORECASE,
        )
        if technical.search(text):
            violations.append("no technical implementation or metric terminology")
        unsupported = re.compile(
            r"\b(?:guarantees|will definitely increase|will definitely decrease)\b",
            re.IGNORECASE,
        )
        if unsupported.search(text):
            violations.append("no unsupported forecast, guarantee, or business recommendation")
        return violations

    @staticmethod
    def _grounding_violations(text: str, facts: SummaryFacts) -> list[str]:
        if (
            facts.execution_type != "REPORT"
            or not (facts.facts or facts.report_breakdown)
        ):
            return []
        empty_claim = re.compile(
            r"\b(?:no|without|absence of|does not contain any|lacks?)\b"
            r".{0,60}\b(?:facts?|data|metrics?|measures?|values?|results?|drivers?)\b|"
            r"(?:somut veri sonuçlarını içermez|hiçbir .{0,40}(?:bulunmamaktadır|yoktur)|"
            r"veri seti boştur?|veri setinin eksik olması|"
            r"(?:ölçülebilir|nicel|sayısal).{0,30}(?:veri|değer|sonuç).{0,20}(?:yok|eksik))",
            re.IGNORECASE,
        )
        return ["use the supplied governed report facts"] if empty_claim.search(text) else []

    @staticmethod
    def _warning_duplication_violations(
        text: str, facts: SummaryFacts,
    ) -> list[str]:
        warning_codes = {warning.code for warning in facts.warnings}
        if "WHAT_IF_NOT_CAUSAL" not in warning_codes:
            return []
        duplicated_warning = re.compile(
            r"\b(?:caus(?:al|ation)|does not prove|controlled experiment|"
            r"real[- ]world effects?|market conditions?|competitors?|demand shifts?|"
            r"customer behavior|not (?:a )?guarantee|cannot guarantee|"
            r"nedensel(?:lik)?|neden[- ]sonuç|garanti|kontrollü deney|"
            r"piyasa koşulları|rakip(?:ler)?|talep değiş(?:imi|iklikleri))\b",
            re.IGNORECASE,
        )
        return (
            ["do not repeat or expand warnings rendered separately"]
            if duplicated_warning.search(text) else []
        )

    @staticmethod
    def _numeric_value(value: Any) -> float | None:
        if isinstance(value, bool) or value is None:
            return None
        try:
            number = Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
        return float(number) if number.is_finite() else None

    @staticmethod
    def _display_number(value: float, language: str) -> str:
        rendered = f"{value:,.2f}".rstrip("0").rstrip(".")
        if language == "tr":
            rendered = rendered.replace(",", "\0").replace(".", ",").replace("\0", ".")
        return rendered

    @staticmethod
    def _grounded_management_fallback(facts: SummaryFacts) -> str:
        if facts.execution_type == "REPORT":
            breakdown = [
                item for item in facts.report_breakdown if item.measures
            ]
            if breakdown:
                measure = next(iter(breakdown[0].measures))
                numeric = [
                    (item, number)
                    for item in breakdown
                    if (number := ResultExplainer._numeric_value(
                        item.measures.get(measure))) is not None
                ]
                if numeric:
                    highest, highest_value = max(numeric, key=lambda item: item[1])
                    displayed_value = ResultExplainer._display_number(
                        highest_value, facts.language)
                    dimension = (
                        next(iter(highest.dimensions.values()))
                        if highest.dimensions else None
                    )
                    label = measure.replace("_", " ")
                    secondary = next(
                        (
                            (name, number)
                            for name, value in highest.measures.items()
                            if name != measure
                            and (number := ResultExplainer._numeric_value(value)) is not None
                        ),
                        None,
                    )
                    secondary_text = (
                        f" {secondary[0].replace('_', ' ')}: "
                        f"{ResultExplainer._display_number(secondary[1], facts.language)}."
                        if secondary else ""
                    )
                    if facts.language == "tr":
                        leader = (
                            f" En yüksek {label} değeri {dimension} için "
                            f"{displayed_value} olarak hesaplandı.{secondary_text}"
                            if dimension is not None else
                            f" Hesaplanan {label} değeri {displayed_value}.{secondary_text}"
                        )
                        return (
                            f"Analiz {len(breakdown)} karşılaştırılabilir toplu sonuç üretti."
                            f"{leader} Bu görünüm, kapsamdaki grupları aynı ölçüte göre "
                            "karşılaştırmak için kullanılabilir. Sonuç yalnızca seçilen veri, "
                            "tarih aralığı ve filtreleri yansıtır."
                        )
                    leader = (
                        f" The highest {label} is {displayed_value} for {dimension}."
                        f"{secondary_text}"
                        if dimension is not None else
                        f" The calculated {label} is {displayed_value}.{secondary_text}"
                    )
                    return (
                        f"The analysis produced {len(breakdown)} comparable aggregate results."
                        f"{leader} This view supports comparison of the in-scope groups using "
                        "the same measure. The result reflects only the selected data, period, "
                        "and filters."
                    )
            if facts.language == "tr":
                return (
                    "İstenen analiz tamamlandı ve doğrulanmış göstergeler karar desteği için "
                    "hazır. Ayrıntılı sonuç kartları karşılaştırılması gereken değerleri gösterir. "
                    "Sonuç yalnızca seçilen veri ve koşulları yansıtır; kapsam dışındaki dönemler "
                    "veya etkenler hakkında çıkarım yapmaz."
                )
            return (
                "The requested analysis is complete and its governed indicators are ready for "
                "decision support. The detailed result cards show the values available for "
                "comparison. The result reflects only the selected data and conditions; it does "
                "not establish conclusions about periods or factors outside that scope."
            )
        if facts.scenarios and facts.scenario_objective:
            selected = (
                max(facts.scenarios, key=lambda item: item.delta_percent)
                if facts.scenario_objective == "MAXIMIZE_TARGET"
                else min(facts.scenarios, key=lambda item: item.delta_percent)
            )
            if facts.language == "tr":
                changes = ", ".join(
                    f"{item.column.replace('_', ' ')} değerinin göreli olarak "
                    f"%{abs(item.percent_change):g} "
                    f"{'artırıldığı' if item.percent_change > 0 else 'azaltıldığı'}"
                    for item in selected.changes
                )
                return (
                    f"Test edilen varsayımlar altında {changes} senaryosu, beklenen net satış "
                    f"tutarında başlangıca göre %{selected.delta_percent:+.2f} ile incelenen "
                    "seçenekler arasındaki en güçlü iyileşmeyi sağladı. Yönetim bu seçeneği genel "
                    "bir değişiklik olarak hemen uygulamak yerine, sınırlı bir pilot uygulamada "
                    "öncelikle test edebilir."
                )
            changes = ", ".join(
                f"{item.column.replace('_', ' ')} was relatively "
                f"{'increased' if item.percent_change > 0 else 'reduced'} by "
                f"{abs(item.percent_change):g}%"
                for item in selected.changes
            )
            return (
                f"Under the tested assumptions, the {changes} scenario produced the strongest "
                f"improvement in expected net sales among the options examined: "
                f"{selected.delta_percent:+.2f}% versus the baseline. Management can prioritize "
                "this option for a limited, controlled business test rather than apply it "
                "company-wide immediately."
            )
        drivers = [
            item.feature.replace("_", " ").strip()
            for item in facts.drivers[:3]
        ]
        r2 = next(
            (
                float(item.value)
                for item in facts.facts
                if item.code == "R2" and isinstance(item.value, (int, float))
            ),
            None,
        )
        reliability = (
            "very consistently" if r2 is not None and r2 >= 0.95
            else "consistently" if r2 is not None and r2 >= 0.8
            else "with some uncertainty"
        )
        if facts.language == "tr":
            driver_text = (
                f"Sonucu en çok {', '.join(drivers[:2])}"
                + (f"; daha sınırlı olarak {drivers[2]}" if len(drivers) > 2 else "")
                + " etkiliyor."
                if drivers else ""
            )
            return (
                f"Mevcut sipariş bilgileriyle beklenen net satış tutarı {reliability.replace('very consistently', 'oldukça tutarlı').replace('consistently', 'tutarlı').replace('with some uncertainty', 'belirli bir belirsizlikle')} tahmin edilebilir. "
                f"{driver_text} Bu sonuç, planlanan siparişleri karşılaştırmak ve ayrıca incelenmesi "
                "gereken tahminleri belirlemek için kullanılabilir. Talebi, satış büyümesini veya "
                "bir politika değişikliğinin etkisini öngörmez; mevcut verideki ilişkileri yansıtır. "
                "Artırma veya azaltma kararı için ilgili girdileri kontrollü biçimde değiştiren "
                "bir senaryo analizi gerekir."
            ).strip()
        driver_text = (
            f"The strongest influences are {', '.join(drivers[:2])}"
            + (f", with {drivers[2]} having a smaller influence" if len(drivers) > 2 else "")
            + "."
            if drivers else ""
        )
        return (
            f"Expected net sales can be estimated {reliability} from the available order "
            f"information. {driver_text} This can support comparison of planned orders and help "
            "identify estimates that deserve review. It does not predict demand, sales growth, "
            "or the effect of changing business policy; it reflects relationships in the "
            "available historical data. An increase or decrease decision requires a governed "
            "what-if analysis that changes the relevant inputs under controlled assumptions."
        ).strip()
