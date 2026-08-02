import json
import logging
from typing import Any, Literal

from pydantic import Field

from kozmik_executor.chat.models import ContractModel, EffectiveLlmConfiguration
from kozmik_executor.chat.providers import ProviderError, ProviderRegistry
from kozmik_executor.execution.models import ExecutionCommand

logger = logging.getLogger(__name__)


class SanitizedFailure(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    failure_code: str = Field(pattern=r"^[A-Z0-9_]{1,100}$")
    failed_stage: str = Field(pattern=r"^[A-Z0-9_]{1,100}$")
    technical_reason: str = Field(min_length=1, max_length=1000)
    user_explanation: str = Field(min_length=1, max_length=2000)
    explanation_status: Literal["COMPLETED", "FAILED"]
    retryable: bool
    language: Literal["tr", "en"]


class FailureExplainer:
    MAX_PROMPT_JSON = 4000

    def __init__(self, registry: ProviderRegistry | None = None) -> None:
        self.registry = registry or ProviderRegistry()

    @staticmethod
    def _language(command: ExecutionCommand) -> Literal["tr", "en"]:
        return "tr" if command.order.requested_language.lower().startswith("tr") else "en"

    def sanitize(
        self, command: ExecutionCommand, exception: Exception, code: str,
    ) -> tuple[str, str, bool]:
        del exception  # Raw exception text must remain in protected logs only.
        if command.execution_type == "REPORT":
            payload = command.order.payload
            aggregation_sources = {
                item.column for item in payload.aggregations if item.column is not None
            }
            temporal_outputs = {
                (item.column, item.alias) for item in payload.temporal_group_by
            }
            if payload.aggregations and any(
                item.column not in payload.group_by
                and item.column not in aggregation_sources
                and (item.column, item.alias or item.column) not in temporal_outputs
                for item in payload.select
            ):
                return (
                    "REPORT_ORDER_SHAPE_INVALID",
                    "The approved report plan mixed row-level selections with an overall "
                    "aggregation, so fields required by later operations were unavailable.",
                    False,
                )
        reasons = {
            "EXECUTION_ORDER_INVALID": (
                "The approved execution instruction did not match the authorized execution context.",
                False,
            ),
            "SCHEMA_VERSION_MISMATCH": (
                "The governed dataset schema version did not match the approved execution instruction.",
                False,
            ),
            "GOVERNED_DATASET_NOT_FOUND": (
                "No completed governed dataset was available for the selected entity and schema version.",
                False,
            ),
            "GOVERNED_DATASET_BINDING_MISMATCH": (
                "The resolved governed dataset did not belong to the approved entity and schema version.",
                False,
            ),
            "SPARK_JOB_FAILED": (
                "Spark could not complete the approved operation using the governed dataset.",
                False,
            ),
            "SPARK_RUNTIME_UNAVAILABLE": (
                "The Spark execution runtime became unavailable while processing the operation.",
                True,
            ),
            "ML_TUNING_CONFIGURATION_UNSAFE": (
                "Spark rejected the approved tuning configuration because its model graph "
                "exceeded the safe execution limit.",
                True,
            ),
        }
        technical, retryable = reasons.get(
            code, ("The execution engine could not complete the approved operation.", False))
        return code, technical, retryable

    @staticmethod
    def fallback(
        language: Literal["tr", "en"], failure_code: str, technical_reason: str,
    ) -> str:
        if failure_code == "REPORT_ORDER_SHAPE_INVALID":
            return (
                "Rapor planı satır düzeyindeki alanları genel bir toplama işlemiyle "
                "birleştirdi. Toplama sonrasında sıralama veya seçim için gereken alanlar "
                "artık mevcut değildi ve çalışma güvenli biçimde durduruldu. Tekil kayıtları "
                "listelemek için toplama kullanmayın; toplamlar için alanları açıkça gruplandırın."
                if language == "tr"
                else
                "The report plan combined row-level fields with an overall aggregation. "
                "After aggregation, fields needed for selection or sorting were no longer "
                "available, so execution was stopped safely. List individual records without "
                "aggregation, or explicitly group fields when requesting totals."
            )
        return (
            f"Çalışma güvenli biçimde tamamlanamadı. Neden: {technical_reason}"
            if language == "tr"
            else f"The execution could not be completed safely. Reason: {technical_reason}"
        )

    async def explain(
        self, command: ExecutionCommand, exception: Exception, code: str,
        failed_stage: str = "RUNNING",
    ) -> SanitizedFailure:
        language = self._language(command)
        failure_code, technical_reason, retryable = self.sanitize(
            command, exception, code)
        fallback = self.fallback(language, failure_code, technical_reason)
        safe_facts: dict[str, Any] = {
            "schemaVersion": "1.0",
            "failureCode": failure_code,
            "failedStage": failed_stage,
            "technicalReason": technical_reason,
            "executionType": command.execution_type,
            "language": language,
            "retryable": retryable,
        }
        encoded = json.dumps(safe_facts, separators=(",", ":"), ensure_ascii=False)
        if len(encoded) > self.MAX_PROMPT_JSON:
            return SanitizedFailure(
                failureCode=failure_code, failedStage=failed_stage,
                technicalReason=technical_reason, userExplanation=fallback,
                explanationStatus="FAILED", retryable=retryable, language=language)
        try:
            llm = EffectiveLlmConfiguration.model_validate(command.configuration["llm"])
            provider = self.registry.resolve(llm)
            instruction = (
                "Explain this sanitized execution failure to a non-technical user. "
                "Use only the supplied facts. Do not mention stack traces, SQL, code, "
                "storage paths, infrastructure, customers, or raw data. Give one concise "
                "reason and one corrective suggestion. Respond in "
                + ("Turkish." if language == "tr" else "English.")
            )
            chunks: list[str] = []
            length = 0
            async for chunk in provider.stream([
                {"role": "system", "content": instruction},
                {"role": "user", "content": encoded},
            ]):
                length += len(chunk)
                if length > 2000:
                    raise ProviderError("LLM_FAILURE_EXPLANATION_TOO_LARGE")
                chunks.append(chunk)
            explanation = "".join(chunks).strip()
            if not explanation:
                raise ProviderError("LLM_FAILURE_EXPLANATION_EMPTY")
            status: Literal["COMPLETED", "FAILED"] = "COMPLETED"
        except (ProviderError, ValueError, KeyError) as provider_exception:
            logger.warning(
                "failure_explanation_failed code=FAILURE_EXPLANATION_FAILED "
                "exceptionType=%s", type(provider_exception).__name__)
            explanation = fallback
            status = "FAILED"
        return SanitizedFailure(
            failureCode=failure_code, failedStage=failed_stage,
            technicalReason=technical_reason, userExplanation=explanation,
            explanationStatus=status, retryable=retryable, language=language)
