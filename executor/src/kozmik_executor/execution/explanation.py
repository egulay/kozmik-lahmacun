import json
import logging
import re
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Literal

from pydantic import ValidationError

from lingua import Language, LanguageDetectorBuilder

from kozmik_executor.chat.models import ContractModel, EffectiveLlmConfiguration
from kozmik_executor.chat.providers import ProviderError, ProviderRegistry
from kozmik_executor.execution.management_evidence import (
    ManagementEvidence,
    ManagementEvidenceBuilder,
    RecommendationAuthority,
)
from kozmik_executor.execution.management_summary import (
    ManagementSummaryAudit,
    ProviderManagementProse,
    SummaryValidation,
    SummaryViolation,
    ViolationSeverity,
    evidence_index,
    expected_scope,
)
from kozmik_executor.execution.models import ExecutionCommand

logger = logging.getLogger(__name__)


class ExplanationOutcome(ContractModel):
    status: Literal["COMPLETED", "FAILED"]
    text: str | None = None
    evidence: ManagementEvidence
    validation_status: Literal[
        "ACCEPTED", "ACCEPTED_WITH_ADVISORIES", "REJECTED", "PROVIDER_FAILED"
    ]
    validation_issues: list[str]
    blocking_issues: list[str]
    advisory_issues: list[str]
    summary_audit: ManagementSummaryAudit | None = None
    repair_attempt_count: int
    provider: str
    provider_model: str
    generated_at: datetime


class ManagementSummaryValidator:
    _CURRENCY_PATTERNS = {
        "EUR": r"\b(?:eur|euro\w*|avro\w*)\b|€",
        "USD": r"\b(?:usd|dollars?|dolar\w*)\b|\$",
        "TRY": r"\b(?:try|tl|turkish lira|türk lirası\w*|lira\w*)\b|₺",
        "GBP": r"\b(?:gbp|pounds? sterling|sterlin\w*)\b|£",
        "JPY": r"\b(?:jpy|yen)\b|¥",
        "CNY": r"\b(?:cny|yuan|renminbi)\b",
    }
    _UNIT_PATTERNS = {
        "SECOND": r"\b(?:seconds|secs?|saniye)\b|(?<!\w)\d+(?:[.,]\d+)?\s*second\b",
        "MINUTE": r"\b(?:minutes?|mins?|dakika)\b",
        "HOUR": r"\b(?:hours?|hrs?|saat)\b",
        "DAY": r"\b(?:days?|gün)\b",
        "PERCENT": r"%|\b(?:percent(?:age)?|yüzde)\b",
        "KILOGRAM": r"\b(?:kilograms?|kilogrammes?|kg|kilogram)\b",
        "GRAM": r"\b(?:grams?|grammes?|gram)\b",
        "TONNE": r"\b(?:tonnes?|metric tons?|ton)\b",
        "METRE": r"\b(?:metres?|meters?|metre|metreler|metre)\b",
        "KILOMETRE": r"\b(?:kilometres?|kilometers?|km|kilometre)\b",
        "LITRE": r"\b(?:litres?|liters?|litre|litreler)\b",
    }

    def validate(
        self, text: str, evidence: ManagementEvidence,
    ) -> SummaryValidation:
        violations: list[SummaryViolation] = []
        if not text.strip():
            violations.append(self._blocking(
                "EMPTY_SUMMARY", "Return a non-empty management explanation."
            ))
            return SummaryValidation(status="REJECTED", violations=violations)
        violations.extend(self._unit_violations(text, evidence))
        violations.extend(self._numeric_grounding_violations(text, evidence))
        violations.extend(self._language_violations(text, evidence))
        violations.extend(self._causality_violations(text, evidence))
        violations.extend(self._recommendation_violations(text, evidence))
        violations.extend(self._warning_violations(text, evidence))
        violations.extend(self._narrative_advisories(text, evidence))
        if evidence.result_row_count == 0:
            violations.extend(self._zero_result_violations(text))
        elif evidence.execution_type == "REPORT":
            violations.extend(self._report_violations(text, evidence))
        else:
            violations.extend(self._ml_violations(text, evidence))
        status = (
            "REJECTED"
            if any(item.severity == ViolationSeverity.BLOCKING for item in violations)
            else "ACCEPTED_WITH_ADVISORIES" if violations else "ACCEPTED"
        )
        return SummaryValidation(status=status, violations=violations)

    @staticmethod
    def _blocking(code: str, instruction: str) -> SummaryViolation:
        return SummaryViolation(
            code=code, severity=ViolationSeverity.BLOCKING,
            repairInstruction=instruction,
        )

    @staticmethod
    def _advisory(code: str, instruction: str) -> SummaryViolation:
        return SummaryViolation(
            code=code, severity=ViolationSeverity.ADVISORY,
            repairInstruction=instruction,
        )

    def _unit_violations(
        self, text: str, evidence: ManagementEvidence,
    ) -> list[SummaryViolation]:
        # Governed labels can legitimately contain unit-like tokens (for example
        # ``duration_seconds``). They are names, not narrative unit assertions.
        text = self._without_governed_labels(text, evidence)
        report_measures = [
            *(item.measure for item in evidence.report_measure_results),
            *(item.measure for item in evidence.report_comparisons),
            *(item.measure for item in evidence.time_changes),
            *(item.measure for item in evidence.report_highlights),
            *(item.numerator for item in evidence.normalized_comparisons),
            *(item.denominator for item in evidence.normalized_comparisons),
        ]
        supplied_units = {
            item.unit.upper()
            for item in report_measures
            if isinstance(item.unit, str)
        } | {
            item.unit.upper()
            for item in evidence.metrics
            if isinstance(item.unit, str)
        }
        if any(
            item.relative_spread is not None
            or item.highest_share_of_total_percent is not None
            for item in evidence.report_comparisons
        ) or any(item.percentage_change is not None for item in evidence.time_changes):
            supplied_units.add("PERCENT")
        if evidence.scenarios:
            supplied_units.add("PERCENT")
        for currency, pattern in self._CURRENCY_PATTERNS.items():
            if re.search(pattern, text, re.IGNORECASE) and currency not in supplied_units:
                return [self._blocking(
                    "UNAPPROVED_CURRENCY",
                    "Remove the currency name or symbol because no approved evidence supplies it.",
                )]
        for unit, pattern in self._UNIT_PATTERNS.items():
            if re.search(pattern, text, re.IGNORECASE) and unit not in supplied_units:
                return [self._blocking(
                    "UNAPPROVED_UNIT",
                    "Remove the unit because no approved evidence supplies that unit.",
                )]
        if re.search(r"\bunits?\b|\bbirim(?:ler|i)?\b", text, re.IGNORECASE):
            return [self._blocking(
                "UNAPPROVED_UNIT",
                "Remove the generic word unit; use only an explicitly supplied governed unit "
                "or currency, otherwise state the calculated value without one.",
            )]
        return []

    def _numeric_grounding_violations(
        self, text: str, evidence: ManagementEvidence,
    ) -> list[SummaryViolation]:
        approved = self._approved_numbers(evidence)
        for match in re.finditer(
            r"(?<![\w])[-+]?\d(?:[\d.,]*\d)?(?![\w])",
            text,
        ):
            parsed = self._parse_display_number(match.group())
            if parsed is None:
                continue
            suffix = text[match.end():match.end() + 12].casefold().lstrip()
            scale = 1.0
            if suffix.startswith(("million", "milyon")):
                scale = 1_000_000.0
            elif suffix.startswith(("billion", "milyar")):
                scale = 1_000_000_000.0
            elif suffix.startswith(("thousand", "bin")):
                scale = 1_000.0
            parsed *= scale
            decimals = self._display_decimal_places(match.group())
            tolerance = max(0.5 * scale * (10 ** -decimals), abs(parsed) * 0.000_001)
            if not any(abs(parsed - value) <= tolerance for value in approved):
                return [self._blocking(
                    "UNAPPROVED_NUMBER",
                    f"Remove or correct the unsupported number {match.group()}; use only "
                    "numbers present in the evidence contract.",
                )]
        return []

    @classmethod
    def _approved_numbers(cls, evidence: ManagementEvidence) -> set[float]:
        values = {float(evidence.result_row_count)}
        for row in evidence.report_breakdown:
            values.update(cls._numbers_in_dimensions(row))
        for item in evidence.report_measure_results:
            values.add(item.value)
        for item in evidence.report_comparisons:
            values.update((
                item.highest.value, item.lowest.value, item.absolute_spread,
                float(item.group_count), float(item.highest_tie_count),
                float(item.lowest_tie_count),
            ))
            if item.relative_spread:
                values.add(item.relative_spread.percent)
            if item.highest_share_of_total_percent is not None:
                values.add(item.highest_share_of_total_percent)
            for dimension in (item.highest.dimensions, item.lowest.dimensions):
                values.update(cls._numbers_in_dimensions(dimension))
        for item in evidence.normalized_comparisons:
            values.update((item.highest.value, item.lowest.value, item.absolute_spread))
            if item.relative_spread:
                values.add(item.relative_spread.percent)
            values.update(cls._numbers_in_dimensions(item.highest.dimensions))
            values.update(cls._numbers_in_dimensions(item.lowest.dimensions))
        for item in evidence.time_changes:
            values.update((item.earlier.value, item.later.value, item.absolute_change))
            values.add(abs(item.absolute_change))
            if item.percentage_change is not None:
                values.add(item.percentage_change)
                values.add(abs(item.percentage_change))
            values.update(cls._numbers_in_dimensions(item.earlier.dimensions))
            values.update(cls._numbers_in_dimensions(item.later.dimensions))
        for item in evidence.report_highlights:
            values.add(item.value)
            values.update(cls._numbers_in_text(item.leading_category))
        for item in evidence.metrics:
            values.add(item.value)
        for item in evidence.drivers:
            values.add(item.importance)
        if evidence.model_selection:
            selection = evidence.model_selection
            values.update(
                float(value) for value in (
                    selection.candidate_algorithms_evaluated,
                    selection.tuning_trials_evaluated,
                    selection.validation_score,
                ) if value is not None
            )
        for item in evidence.scenarios:
            values.add(item.delta_percent)
            values.add(abs(item.delta_percent))
            values.update(
                float(value) for value in (
                    item.baseline_prediction, item.scenario_prediction, item.delta,
                ) if value is not None
            )
            if item.delta is not None:
                values.add(abs(item.delta))
            for change in item.changes:
                values.add(change.percent_change)
                values.add(abs(change.percent_change))
        return {value for value in values if value == value}

    @classmethod
    def _numbers_in_dimensions(cls, values: dict[str, Any]) -> set[float]:
        approved = set()
        for value in values.values():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                approved.add(float(value))
            elif isinstance(value, str):
                approved.update(cls._numbers_in_text(value))
        return approved

    @classmethod
    def _numbers_in_text(cls, value: str) -> set[float]:
        approved = set()
        for match in re.finditer(r"(?<![\w])[-+]?\d(?:[\d.,]*\d)?(?![\w])", value):
            parsed = cls._parse_display_number(match.group())
            if parsed is not None:
                approved.add(parsed)
                approved.add(abs(parsed))
        return approved

    @staticmethod
    def _parse_display_number(value: str) -> float | None:
        normalized = value.strip()
        if not normalized:
            return None
        comma = normalized.rfind(",")
        dot = normalized.rfind(".")
        if comma >= 0 and dot >= 0:
            decimal = "," if comma > dot else "."
            thousands = "." if decimal == "," else ","
            normalized = normalized.replace(thousands, "").replace(decimal, ".")
        elif normalized.count(",") > 1:
            normalized = normalized.replace(",", "")
        elif normalized.count(".") > 1:
            normalized = normalized.replace(".", "")
        elif comma >= 0:
            tail = len(normalized) - comma - 1
            normalized = (
                normalized.replace(",", "") if tail == 3
                else normalized.replace(",", ".")
            )
        try:
            return float(normalized)
        except ValueError:
            return None

    @staticmethod
    def _display_decimal_places(value: str) -> int:
        comma = value.rfind(",")
        dot = value.rfind(".")
        position = max(comma, dot)
        if position < 0:
            return 0
        tail = len(value) - position - 1
        return 0 if tail == 3 and value.count(",") + value.count(".") == 1 else tail

    def _causality_violations(
        self, text: str, evidence: ManagementEvidence,
    ) -> list[SummaryViolation]:
        causal = re.compile(
            r"\b(?:causes?|caused(?: by)?|will result in|guarantees?|proves? that|"
            r"neden olur|sebep olur|sonuç doğurur|garanti eder|kanıtlar?)\b",
            re.IGNORECASE,
        )
        # A provider may correctly state that the result *does not* establish causality.
        # Remove those explicit negated clauses before looking for positive causal claims.
        asserted_text = re.sub(
            r"\b(?:does not|do not|did not|cannot|can't|is not|are not|"
            r"değildir|göstermez|kanıtlamaz)\b[^.!?]{0,80}\b(?:causes?|caused|"
            r"proves?|guarantees?|neden olur|sebep olur|kanıtlar?)\b",
            " ",
            text,
            flags=re.IGNORECASE,
        )
        if causal.search(asserted_text) and not evidence.policy.causal_claims_allowed:
            return [self._blocking(
                "UNSUPPORTED_CAUSALITY",
                "Describe association or calculated scenario difference, not causality or guarantees.",
            )]
        return []

    @staticmethod
    @lru_cache(maxsize=1)
    def _language_detector():
        return LanguageDetectorBuilder.from_languages(
            Language.ENGLISH, Language.TURKISH,
        ).build()

    def _language_violations(
        self, text: str, evidence: ManagementEvidence,
    ) -> list[SummaryViolation]:
        sanitized = self._without_governed_labels(text, evidence)
        words = re.findall(r"[^\W\d_]+", sanitized, flags=re.UNICODE)
        if len(words) < 8:
            return []
        detected = self._language_detector().detect_language_of(sanitized)
        expected = Language.TURKISH if evidence.language == "tr" else Language.ENGLISH
        if detected is not None and detected != expected:
            return [self._blocking(
                "WRONG_LANGUAGE",
                "Rewrite the entire summary in the requested evidence language.",
            )]
        for segment in re.split(r"(?:\n+|(?<=[.!?])\s+)", sanitized):
            segment_words = re.findall(r"[^\W\d_]+", segment, flags=re.UNICODE)
            if len(segment_words) < 6:
                continue
            segment_language = self._language_detector().detect_language_of(segment)
            if segment_language is not None and segment_language != expected:
                return [self._blocking(
                    "MIXED_LANGUAGE",
                    "Rewrite every narrative sentence in the requested language; retain only "
                    "governed labels or names that have no localized display label.",
                )]
        return []

    @staticmethod
    def _without_governed_labels(text: str, evidence: ManagementEvidence) -> str:
        labels = {
            *(item.measure.label for item in evidence.report_measure_results),
            *(item.measure.label for item in evidence.report_comparisons),
            *(item.measure.label for item in evidence.time_changes),
            *(item.measure.label for item in evidence.report_highlights),
            *(item.numerator.label for item in evidence.normalized_comparisons),
            *(item.denominator.label for item in evidence.normalized_comparisons),
            *(item.label for item in evidence.metrics),
            *(item.feature for item in evidence.drivers),
        }
        if evidence.target:
            labels.add(evidence.target)
        sanitized = text
        for label in sorted(labels, key=len, reverse=True):
            if label:
                sanitized = re.sub(re.escape(label), " ", sanitized, flags=re.IGNORECASE)
        return sanitized

    def _recommendation_violations(
        self, text: str, evidence: ManagementEvidence,
    ) -> list[SummaryViolation]:
        directional = re.compile(
            r"\b(?:should\s+(?:increase|decrease|raise|reduce|expand|cut|maintain|"
            r"change|adjust|prioriti[sz]e)|recommend(?:s|ed|ation)?\s+(?:increasing|"
            r"decreasing|raising|reducing|changing|adjusting|prioriti[sz]ing)|must\s+"
            r"(?:increase|decrease|change|adjust)|prioriti[sz]e\s+(?:this|the)|"
            r"artırmalı|azaltmalı|öncelik\s+verilmeli|değiştirilmeli|yükseltmeli|"
            r"düşürmeli|korumalı|(?:artırma|azaltma|değiştirme)\s+önerilir)\b",
            re.IGNORECASE,
        )
        if (
            directional.search(text)
            and evidence.policy.recommendation_authority == RecommendationAuthority.NONE
        ):
            return [self._blocking(
                "UNSUPPORTED_RECOMMENDATION",
                "Remove directional advice; no approved scenario evidence authorizes it.",
            )]
        if directional.search(text):
            selected = next(
                (
                    item for item in evidence.scenarios
                    if item.code == evidence.policy.authorized_scenario_code
                ),
                None,
            )
            if selected is None:
                return [self._blocking(
                    "RECOMMENDATION_WITHOUT_AUTHORIZED_SCENARIO",
                    "Remove the recommendation because no scenario is authorized for it.",
                )]
            required_increase = any(
                item.percent_change > 0 for item in selected.changes
            )
            required_decrease = any(
                item.percent_change < 0 for item in selected.changes
            )
            increase = re.compile(
                r"\b(?:increase|raise|expand|artır|yükselt)", re.IGNORECASE
            )
            decrease = re.compile(
                r"\b(?:decrease|reduce|cut|azalt|düşür)", re.IGNORECASE
            )
            if required_increase and not increase.search(text):
                return [self._blocking(
                    "RECOMMENDATION_DIRECTION_MISMATCH",
                    f"Base conditional advice only on authorized scenario {selected.code}.",
                )]
            if required_decrease and not decrease.search(text):
                return [self._blocking(
                    "RECOMMENDATION_DIRECTION_MISMATCH",
                    f"Base conditional advice only on authorized scenario {selected.code}.",
                )]
        return []

    def _warning_violations(
        self, text: str, evidence: ManagementEvidence,
    ) -> list[SummaryViolation]:
        violations: list[SummaryViolation] = []
        if re.search(
            r"\b(?:not authorized|authorization policy|evidence contract|governed facts?|"
            r"yetkili değil|yetkilendirme politikası|kanıt sözleşmesi|yönetilen olgular)\b",
            text, re.IGNORECASE,
        ):
            violations.append(self._advisory(
                "INTERNAL_POLICY_LANGUAGE",
                "Explain the practical use or absence of calculated scenarios without exposing "
                "internal authorization, evidence-contract, or governance terminology.",
            ))
        warning_codes = {item.code for item in evidence.warnings}
        if "WHAT_IF_NOT_CAUSAL" not in warning_codes:
            return violations
        duplicated = re.compile(
            r"\b(?:does not prove|controlled experiment|not a guarantee|"
            r"market conditions|competitors?|customer behavior|"
            r"nedensel değildir|kontrollü deney|garanti değildir|piyasa koşulları|"
            r"rakipler|müşteri davranışı)\b",
            re.IGNORECASE,
        )
        if duplicated.search(text):
            violations.append(self._advisory(
                "DUPLICATED_WARNING",
                "Remove warnings because the interface renders approved warnings separately.",
            ))
        return violations

    def _narrative_advisories(
        self, text: str, evidence: ManagementEvidence,
    ) -> list[SummaryViolation]:
        violations: list[SummaryViolation] = []
        objective_words = self._narrative_words(evidence.objective)
        opening = re.split(r"(?:\n\n|(?<=[.!?])\s+)", text.strip(), maxsplit=1)[0]
        opening_words = self._narrative_words(opening)
        if len(objective_words) >= 6:
            overlap = len(set(objective_words).intersection(opening_words))
            if overlap / len(set(objective_words)) >= 0.85:
                violations.append(self._advisory(
                    "REQUEST_REPETITION",
                    "Lead with the principal calculated result rather than restating the request.",
                ))
        if re.search(
            r"\b(?:spark|parquet|dataframe|pipeline|hyperparameter|execution order|"
            r"çalıştırma emri|veri çerçevesi|işlem hattı|hiperparametre)\b",
            text,
            re.IGNORECASE,
        ):
            violations.append(self._advisory(
                "EXECUTION_MECHANICS_EXPOSED",
                "Remove implementation mechanics and explain only calculated business meaning.",
            ))
        return violations

    @staticmethod
    def _narrative_words(value: str) -> list[str]:
        return [
            item.casefold() for item in re.findall(r"[^\W\d_]+", value, re.UNICODE)
            if len(item) > 2
        ]

    def _zero_result_violations(self, text: str) -> list[SummaryViolation]:
        no_data = re.compile(
            r"\b(?:no (?:matching )?data|no results?|zero rows)\b|"
            r"(?:eşleşen veri bulunamadı|sonuç bulunamadı|sıfır satır)",
            re.IGNORECASE,
        )
        return (
            [] if no_data.search(text) else [self._blocking(
                "ZERO_RESULT_HALLUCINATION",
                "State that no data matched; do not describe findings that do not exist.",
            )]
        )

    def _report_violations(
        self, text: str, evidence: ManagementEvidence,
    ) -> list[SummaryViolation]:
        violations = []
        normalized = text.casefold()
        empty_claim = re.compile(
            r"\b(?:contains no|does not contain|without any|lacks?)\b.{0,40}"
            r"\b(?:facts?|values?|results?|data)\b|"
            r"(?:veri sonucu içermez|hesaplanmış değer yok|sonuç bulunmamaktadır)",
            re.IGNORECASE,
        )
        if (
            evidence.report_measure_results
            or evidence.report_comparisons
            or evidence.report_highlights
        ) and empty_claim.search(text):
            violations.append(self._blocking(
                "REPORT_FACTS_IGNORED",
                "Use the supplied calculated report comparisons; do not claim they are absent.",
            ))
        evaluative = re.compile(
            r"\b(?:best|worst|top performer|highest performer|lowest performer|"
            r"outperform(?:ed|s)?|underperform(?:ed|s)?|"
            r"en iyi|en kötü|en başarılı|en başarısız|daha iyi performans|"
            r"daha kötü performans)\b",
            re.IGNORECASE,
        )
        if evaluative.search(text):
            violations.append(self._blocking(
                "UNSUPPORTED_REPORT_DIRECTIONALITY",
                "Use highest/lowest recorded value, not best/worst performance; report direction is context-dependent.",
            ))
        spread_misuse = re.compile(
            r"(?:%\s*\d+(?:[.,]\d+)?|\d+(?:[.,]\d+)?\s*%).{0,50}"
            r"(?:of (?:the )?total|change|increase|decrease|growth|decline|"
            r"toplamın|değişim|artış|azalış|büyüme|düşüş)|"
            r"(?:of (?:the )?total|change|increase|decrease|growth|decline|"
            r"toplamın|değişim|artış|azalış|büyüme|düşüş).{0,50}"
            r"(?:%\s*\d+(?:[.,]\d+)?|\d+(?:[.,]\d+)?\s*%)",
            re.IGNORECASE,
        )
        relative_spreads = [
            item.relative_spread.percent
            for item in evidence.report_comparisons
            if item.relative_spread is not None
        ]
        for match in spread_misuse.finditer(text):
            displayed = [
                self._parse_display_number(item.group())
                for item in re.finditer(r"\d+(?:[.,]\d+)?", match.group())
            ]
            if any(
                value is not None and any(
                    abs(value - spread) <= max(0.005, abs(value) * 0.000_001)
                    for spread in relative_spreads
                )
                for value in displayed
            ):
                violations.append(self._blocking(
                    "RELATIVE_SPREAD_MISSTATED",
                    "Describe relativeSpreadPercent only as the symmetric relative spread "
                    "between the highest and lowest values; never as share of total or "
                    "temporal change.",
                ))
                break
        for comparison in evidence.report_comparisons[:3]:
            high_labels = self._dimension_labels(comparison.highest.dimensions)
            low_labels = self._dimension_labels(comparison.lowest.dimensions)
            if high_labels and not any(value in normalized for value in high_labels):
                violations.append(self._advisory(
                    "HIGHEST_GROUP_OMITTED",
                    f"Identify the highest recorded group for {comparison.measure.label}.",
                ))
            if low_labels and not any(value in normalized for value in low_labels):
                violations.append(self._advisory(
                    "LOWEST_GROUP_OMITTED",
                    f"Identify the lowest recorded group for {comparison.measure.label}.",
                ))
        technical = re.compile(
            r"\b(?:governed facts?|reportbreakdown|symmetric percent difference)\b",
            re.IGNORECASE,
        )
        if technical.search(text):
            violations.append(self._advisory(
                "TECHNICAL_REPORT_LANGUAGE",
                "Use ordinary business language without contract or calculation-method names.",
            ))
        return self._deduplicate(violations)

    def _ml_violations(
        self, text: str, evidence: ManagementEvidence,
    ) -> list[SummaryViolation]:
        violations = []
        metric_codes = {item.code for item in evidence.metrics}
        if metric_codes.intersection({"MAE", "RMSE", "R2", "AUC", "F1"}) and re.search(
            r"\b(?:metrics? (?:measure|measures|show|shows|indicate|indicates) "
            r"(?:the )?(?:model(?:'s)? )?accuracy|model(?:'s)? accuracy (?:is )?"
            r"measured (?:by|with)|metrikler? model doğruluğunu (?:ölçer|gösterir))\b",
            text, re.IGNORECASE,
        ):
            violations.append(self._blocking(
                "METRICS_MISLABELED_AS_ACCURACY",
                "Do not collectively label error, variation, ranking, or F1 measurements as accuracy.",
            ))
        if "RMSE" in metric_codes and re.search(
            r"\b(?:average|mean) (?:error |prediction )?magnitude\b|"
            r"\bortalama hata büyüklüğü\b", text, re.IGNORECASE,
        ):
            violations.append(self._blocking(
                "RMSE_MEAN_MAGNITUDE_MISSTATED",
                "Explain the square root of mean squared error and its greater sensitivity to larger errors.",
            ))
        if evidence.drivers and re.search(
            r"\b(?:contribut\w* to|improv\w*).{0,30}\baccuracy\b|"
            r"\bdoğruluğa katkı\b", text, re.IGNORECASE,
        ):
            violations.append(self._blocking(
                "FEATURE_IMPORTANCE_INTERPRETATION_UNSUPPORTED",
                "Feature importance indicates model reliance only, not contribution to accuracy.",
            ))
        if re.search(
            r"\b(?:highly reliable|reliable model|strong performance|weak performance|"
            r"good performance|poor performance|acceptable performance|actionable|"
            r"production[- ]ready|yüksek güvenilir|güvenilir model|güçlü performans|"
            r"zayıf performans|kabul edilebilir|eyleme hazır|üretime hazır)\b",
            text, re.IGNORECASE,
        ):
            violations.append(self._blocking(
                "QUALITATIVE_PERFORMANCE_UNSUPPORTED",
                "Remove qualitative performance or readiness judgments because no typed business "
                "tolerance or acceptance threshold supports them.",
            ))
        for metric in evidence.metrics:
            if metric.code in {"R2", "AUC"} and self._percentage_present(
                text, metric.value
            ):
                misleading = re.compile(
                    rf"(?:confidence|probability|reliability|accuracy|güven|olasılık|"
                    rf"doğruluk).{{0,35}}{self._percentage_pattern(metric.value)}|"
                    rf"{self._percentage_pattern(metric.value)}.{{0,35}}(?:confidence|"
                    rf"probability|reliability|accuracy|güven|olasılık|doğruluk)",
                    re.IGNORECASE,
                )
                if misleading.search(text):
                    violations.append(self._blocking(
                        "METRIC_MEANING_MISSTATED",
                        f"Use the supplied business definition for {metric.code}; it is not "
                        "confidence, probability, reliability, or general accuracy.",
                    ))
            if metric.code in {"MAE", "RMSE"} and self._percentage_present(
                text, metric.value
            ):
                violations.append(self._blocking(
                    "ERROR_METRIC_UNIT_MISSTATED",
                    f"Do not add a percent sign to {metric.code}; no percent unit is supplied.",
                ))
        if evidence.drivers:
            directional_driver = re.compile(
                r"\b(?:increasing|decreasing|raises?|reduces?|drives? up|drives? down|"
                r"artırmak|azaltmak|yükseltir|düşürür)\b",
                re.IGNORECASE,
            )
            if directional_driver.search(text) and not evidence.scenarios:
                violations.append(self._blocking(
                    "UNSUPPORTED_DRIVER_DIRECTION",
                    "Feature importance shows influence strength only; remove increase/decrease direction unless scenario evidence supplies it.",
                ))
        return self._deduplicate(violations)

    @staticmethod
    def _dimension_labels(values: dict[str, Any]) -> list[str]:
        return [
            str(value).casefold()
            for value in values.values()
            if isinstance(value, (str, int, float))
            and not re.match(r"^\d{4}-\d{2}(?:-\d{2})?(?:[tT].*)?$", str(value))
        ]

    @staticmethod
    def _percentage_present(text: str, value: float) -> bool:
        for match in re.finditer(r"(?<!\d)(\d+(?:[.,]\d+)?)\s*%", text):
            try:
                displayed = float(match.group(1).replace(",", "."))
            except ValueError:
                continue
            decimal_part = re.split(r"[.,]", match.group(1), maxsplit=1)
            decimals = len(decimal_part[1]) if len(decimal_part) == 2 else 0
            if abs(displayed - value) <= 0.5 * (10 ** -decimals):
                return True
        return False

    @staticmethod
    def _number_pattern(value: float) -> str:
        candidates = {
            f"{value:.0f}", f"{value:.1f}".rstrip("0").rstrip("."),
            f"{value:.2f}".rstrip("0").rstrip("."),
        }
        return "(?:" + "|".join(
            re.escape(item) for item in sorted(candidates, key=len, reverse=True)
        ) + ")"

    @classmethod
    def _percentage_pattern(cls, value: float) -> str:
        return rf"{cls._number_pattern(value)}\s*%"

    @staticmethod
    def _deduplicate(items: list[SummaryViolation]) -> list[SummaryViolation]:
        return list({item.code: item for item in items}.values())


class ResultExplainer:
    def __init__(
        self, registry: ProviderRegistry | None = None,
        evidence_builder: ManagementEvidenceBuilder | None = None,
        validator: ManagementSummaryValidator | None = None,
    ) -> None:
        self.registry = registry or ProviderRegistry()
        self.evidence_builder = evidence_builder or ManagementEvidenceBuilder()
        self.validator = validator or ManagementSummaryValidator()

    def build_facts(
        self, command: ExecutionCommand, result: dict[str, Any],
    ) -> ManagementEvidence:
        return self.evidence_builder.build(command, result)

    async def explain(
        self, command: ExecutionCommand, result: dict[str, Any],
    ) -> ExplanationOutcome:
        evidence = self.build_facts(command, result)
        generated_at = datetime.now(timezone.utc)
        provider_name = "UNRESOLVED"
        provider_model = "UNRESOLVED"
        repair_attempts = 0
        draft: ManagementSummaryAudit | None = None
        try:
            llm = EffectiveLlmConfiguration.model_validate(command.configuration["llm"])
            provider = self.registry.resolve(llm)
            provider_name = str(getattr(provider, "name", llm.provider))
            provider_model = str(getattr(provider, "model", llm.model))
            logger.info(
                "management_summary_generation_started executionId=%s executionType=%s "
                "evidenceVersion=%s "
                "semanticRegistryVersion=%s provider=%s model=%s",
                command.execution_id, evidence.execution_type, evidence.schema_version,
                evidence.semantic_registry_version, provider_name, provider_model,
            )
            draft, text, validation, repair_attempts = await self._generate_plain_summary(
                provider, evidence,
            )
            blocking = draft is None or validation.status == "REJECTED" or not text
            blocking_issues = [
                item.code for item in validation.violations
                if item.severity == ViolationSeverity.BLOCKING
            ]
            advisory_issues = [
                item.code for item in validation.violations
                if item.severity == ViolationSeverity.ADVISORY
            ]
            if blocking or draft is None or not text:
                logger.warning(
                    "management_summary_rejected code=SUMMARY_PROSE_UNSAFE "
                    "executionId=%s executionType=%s repairAttempts=%s violations=%s",
                    command.execution_id, evidence.execution_type,
                    repair_attempts,
                    ",".join(item.code for item in validation.violations),
                )
                return ExplanationOutcome(
                    status="FAILED", evidence=evidence, validationStatus="REJECTED",
                    validationIssues=[item.code for item in validation.violations],
                    blockingIssues=blocking_issues, advisoryIssues=advisory_issues,
                    summaryAudit=draft, repairAttemptCount=repair_attempts,
                    provider=provider_name, providerModel=provider_model,
                    generatedAt=generated_at,
                )
            if validation.violations:
                logger.info(
                    "management_summary_accepted_with_advisories executionType=%s "
                    "executionId=%s repairAttempts=%s violations=%s",
                    evidence.execution_type, command.execution_id,
                    repair_attempts,
                    ",".join(item.code for item in validation.violations),
                )
            else:
                logger.info(
                    "management_summary_accepted executionId=%s executionType=%s "
                    "repairAttempts=%s",
                    command.execution_id, evidence.execution_type, repair_attempts,
                )
            return ExplanationOutcome(
                status="COMPLETED", text=text, evidence=evidence,
                validationStatus=validation.status,
                validationIssues=[item.code for item in validation.violations],
                blockingIssues=blocking_issues, advisoryIssues=advisory_issues,
                summaryAudit=draft, repairAttemptCount=repair_attempts,
                provider=provider_name, providerModel=provider_model,
                generatedAt=generated_at,
            )
        except (ProviderError, ValidationError, ValueError, KeyError) as exception:
            logger.warning(
                "management_summary_provider_failed code=SUMMARY_GENERATION_FAILED "
                "executionId=%s executionType=%s provider=%s model=%s exceptionType=%s",
                command.execution_id, evidence.execution_type, provider_name, provider_model,
                type(exception).__name__,
            )
            return ExplanationOutcome(
                status="FAILED", evidence=evidence, validationStatus="PROVIDER_FAILED",
                validationIssues=["SUMMARY_PROVIDER_FAILED"],
                blockingIssues=["SUMMARY_PROVIDER_FAILED"], advisoryIssues=[],
                summaryAudit=draft, repairAttemptCount=repair_attempts,
                provider=provider_name, providerModel=provider_model,
                generatedAt=generated_at,
            )


    @staticmethod
    def _merge_validations(*validations: SummaryValidation) -> SummaryValidation:
        violations = list({
            item.code: item
            for validation in validations
            for item in validation.violations
        }.values())
        status = (
            "REJECTED"
            if any(item.severity == ViolationSeverity.BLOCKING for item in violations)
            else "ACCEPTED_WITH_ADVISORIES" if violations else "ACCEPTED"
        )
        return SummaryValidation(status=status, violations=violations)

    async def _generate_plain_summary(
        self, provider, evidence: ManagementEvidence,
    ) -> tuple[
        ManagementSummaryAudit | None, str, SummaryValidation, int,
    ]:
        """Generate provider prose without delegating typed claim metadata to the model."""
        indexed = evidence_index(evidence)
        evidence_ids = list(indexed)
        empty_validation = SummaryValidation(status="REJECTED", violations=[])
        if not evidence_ids:
            return None, "", empty_validation, 0
        facts = [indexed[evidence_id] for evidence_id in evidence_ids]
        calculated_result = evidence.model_dump(by_alias=True, mode="json")
        prior_prose = ""
        validation = empty_validation
        candidate: ManagementSummaryAudit | None = None
        for attempt in range(2):
            payload = {
                "language": evidence.language,
                "originalRequest": evidence.objective,
                "calculatedResult": calculated_result,
                "previousProse": prior_prose or None,
                "validationIssues": [
                    item.model_dump(by_alias=True, mode="json")
                    for item in validation.violations
                ] if attempt else [],
                "outputSchema": ProviderManagementProse.model_json_schema(by_alias=True),
            }
            messages = [{
                "role": "system",
                "content": (
                    "Write the final management summary as prose for a non-technical business "
                    "reader. Return exactly one JSON object matching outputSchema. The service "
                    "owns all claim metadata; you write only prose. Directly answer "
                    "originalRequest using only calculatedResult. Cover every measure and "
                    "comparison requested when calculatedResult supplies it. For grouped reports, "
                    "use reportBreakdown to compare the actual categories instead of making vague "
                    "claims. For machine learning, explain what the calculated estimates or "
                    "classifications can support. Use every supplied ML result that helps answer "
                    "the request: evaluated indicators and their businessDefinition, selected "
                    "approach and comparison facts, input fields, model-reliance fields, and "
                    "calculated scenarios. When the request asks for the selected method or "
                    "reliability indicators, state them and translate their meaning into plain "
                    "business language. Do not merely repeat the request or say that supplied "
                    "details are unavailable. Avoid an implementation diary: do not explain "
                    "training mechanics, tuning mechanics, data-split mechanics, Spark, or code. "
                    "Do not invent units, currencies, causes, directionality, recommendations, "
                    "threshold judgments, or facts. Do not repeat interface warnings. Preserve "
                    "governed display labels exactly. Do not impose or target a response length."
                ),
            }, {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            }]
            try:
                raw = await self._complete(provider, messages)
                prior_prose = self._clean(self._parse_prose_repair(raw).prose)
            except ProviderError:
                raise
            except (ValidationError, ValueError, json.JSONDecodeError):
                logger.warning(
                    "management_summary_plain_recovery_parse_failed attempt=%s", attempt + 1,
                )
                continue
            candidate = ManagementSummaryAudit(
                schemaVersion="2.0", language=evidence.language, prose=prior_prose,
                evidenceIds=evidence_ids, scope=expected_scope(facts),
            )
            # Audit metadata is service-owned; the provider supplies only the prose.
            validation = self.validator.validate(prior_prose, evidence)
            if validation.status != "REJECTED":
                if attempt:
                    validation = self._merge_validations(
                        validation,
                        SummaryValidation(
                            status="ACCEPTED_WITH_ADVISORIES",
                            violations=[SummaryViolation(
                                code="SUMMARY_PROSE_REPAIRED",
                                severity=ViolationSeverity.ADVISORY,
                                repairInstruction=(
                                    "The provider corrected its prose using service-supplied "
                                    "semantic validation feedback."
                                ),
                            )],
                        ),
                    )
                return candidate, prior_prose, validation, attempt
        # Some OpenAI-compatible providers repeat the generic word "unit" even after
        # receiving a precise repair instruction.  Removing that word after an approved
        # numeric value cannot create a new fact or change the value's meaning; it only
        # restores the unitless semantics already present in the evidence contract.
        # Revalidation remains mandatory, so every other unsupported assertion still
        # rejects the summary.
        if validation.status == "REJECTED" and {
            item.code for item in validation.violations
            if item.severity == ViolationSeverity.BLOCKING
        } == {"UNAPPROVED_UNIT"}:
            normalized = self._remove_generic_unit_after_number(prior_prose)
            if normalized != prior_prose:
                normalized_validation = self.validator.validate(normalized, evidence)
                if normalized_validation.status != "REJECTED":
                    candidate = candidate.model_copy(deep=True) if candidate else None
                    if candidate:
                        candidate.prose = normalized
                    normalized_validation = self._merge_validations(
                        normalized_validation,
                        SummaryValidation(
                            status="ACCEPTED_WITH_ADVISORIES",
                            violations=[SummaryViolation(
                                code="UNAPPROVED_GENERIC_UNIT_REMOVED",
                                severity=ViolationSeverity.ADVISORY,
                                repairInstruction=(
                                    "The service removed a provider-invented generic unit word "
                                    "and revalidated the otherwise unchanged prose."
                                ),
                            )],
                        ),
                    )
                    return candidate, normalized, normalized_validation, 1
        salvaged = self._validated_sentence_subset(prior_prose, evidence)
        if salvaged and salvaged != prior_prose:
            salvaged_validation = self.validator.validate(salvaged, evidence)
            if salvaged_validation.status != "REJECTED":
                candidate = candidate.model_copy(deep=True) if candidate else None
                if candidate:
                    candidate.prose = salvaged
                salvaged_validation = self._merge_validations(
                    salvaged_validation,
                    SummaryValidation(
                        status="ACCEPTED_WITH_ADVISORIES",
                        violations=[SummaryViolation(
                            code="UNSAFE_PROVIDER_SENTENCES_EXCLUDED",
                            severity=ViolationSeverity.ADVISORY,
                            repairInstruction=(
                                "The service retained only provider-written sentences that "
                                "independently and collectively passed evidence validation."
                            ),
                        )],
                    ),
                )
                return candidate, salvaged, salvaged_validation, 1
        return candidate, prior_prose, validation, 1

    @staticmethod
    def _remove_generic_unit_after_number(text: str) -> str:
        return re.sub(
            r"(?<=\d)\s+(?:units?|birim(?:ler|i)?)\b",
            "",
            text,
            flags=re.IGNORECASE,
        )

    def _validated_sentence_subset(
        self, text: str, evidence: ManagementEvidence,
    ) -> str:
        sentences = [
            item.strip() for item in re.split(r"(?<=[.!?])\s+", text.strip())
            if item.strip()
        ]
        accepted = [
            sentence for sentence in sentences
            if self.validator.validate(sentence, evidence).status != "REJECTED"
        ]
        if not accepted or len(accepted) == len(sentences):
            return ""
        candidate = " ".join(accepted)
        return candidate if self.validator.validate(candidate, evidence).status != "REJECTED" else ""

    @staticmethod
    def _parse_prose_repair(value: str) -> ProviderManagementProse:
        cleaned = value.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(
                r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE,
            )
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end < start:
            raise ValueError("management summary did not return a JSON object")
        return ProviderManagementProse.model_validate_json(cleaned[start:end + 1])

    @staticmethod
    async def _complete(provider, messages: list[dict[str, str]]) -> str:
        complete_json = getattr(provider, "complete_json", None)
        if callable(complete_json):
            system = messages[0]["content"]
            conversation = "\n\n".join(
                f"{message['role'].upper()}:\n{message['content']}"
                for message in messages[1:]
            )
            value = await complete_json(system, conversation)
            return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        chunks = []
        async for chunk in provider.stream(messages):
            chunks.append(chunk)
        return "".join(chunks).strip()

    @staticmethod
    def _clean(text: str) -> str:
        cleaned = re.sub(
            r"^\s*(?:\*\*)?(?:decision summary|management summary|karar özeti|"
            r"yönetici özeti)(?:\*\*)?\s*:?\s*",
            "", text, flags=re.IGNORECASE,
        )
        cleaned = re.split(
            r"\s*(?:\*\*)?(?:approved warnings|onaylı uyarılar)(?:\*\*)?\s*:?\s*",
            cleaned, maxsplit=1, flags=re.IGNORECASE,
        )[0]
        return cleaned.replace("**", "").replace("__", "").strip()
