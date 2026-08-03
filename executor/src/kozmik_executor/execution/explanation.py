import logging
import re
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic_core import to_jsonable_python

from kozmik_executor.chat.models import ContractModel, EffectiveLlmConfiguration
from kozmik_executor.chat.providers import ProviderError, ProviderRegistry
from kozmik_executor.execution.models import ExecutionCommand

logger = logging.getLogger(__name__)


class ExplanationOutcome(ContractModel):
    status: Literal["COMPLETED", "FAILED", "SKIPPED"]
    text: str | None = None
    provider: str
    provider_model: str
    generated_at: datetime
    error_code: str | None = None


class ResultExplainer:
    def __init__(self, registry: ProviderRegistry | None = None) -> None:
        self.registry = registry or ProviderRegistry()

    async def explain(
        self, command: ExecutionCommand, result: dict[str, Any],
    ) -> ExplanationOutcome:
        generated_at = datetime.now(timezone.utc)
        provider_name = "UNRESOLVED"
        provider_model = "UNRESOLVED"
        try:
            llm = EffectiveLlmConfiguration.model_validate(command.configuration["llm"])
            provider = self.registry.resolve(llm)
            provider_name = str(getattr(provider, "name", llm.provider))
            provider_model = str(getattr(provider, "model", llm.model))
            payload = self._summary_payload(command, result)
            logger.info(
                "result_summary_generation_started executionId=%s executionType=%s "
                "provider=%s model=%s totalRowCount=%s rowsIncluded=%s",
                command.execution_id, command.execution_type, provider_name, provider_model,
                payload["totalRowCount"], payload["resultRows"] is not None,
            )
            text = self._clean(await provider.complete_text(
                self._system_prompt(command.order.requested_language),
                self._json(payload),
            ))
            if not text:
                raise ProviderError("LLM_RESULT_SUMMARY_EMPTY")
            logger.info(
                "result_summary_generation_completed executionId=%s executionType=%s",
                command.execution_id, command.execution_type,
            )
            return ExplanationOutcome(
                status="COMPLETED", text=text, provider=provider_name,
                providerModel=provider_model, generatedAt=generated_at,
            )
        except Exception as exception:
            code = (
                exception.code if isinstance(exception, ProviderError)
                else "RESULT_SUMMARY_INTERNAL_ERROR"
            )
            logger.exception(
                "result_summary_generation_failed executionId=%s executionType=%s "
                "provider=%s model=%s code=%s",
                command.execution_id, command.execution_type, provider_name, provider_model, code,
            )
            return ExplanationOutcome(
                status="FAILED", provider=provider_name, providerModel=provider_model,
                generatedAt=generated_at, errorCode=code,
            )

    @staticmethod
    def _summary_payload(
        command: ExecutionCommand, result: dict[str, Any],
    ) -> dict[str, Any]:
        total_row_count = max(0, int(result.get("rowCount", 0)))
        preview = result.get("preview")
        preview = preview if isinstance(preview, dict) else {}
        schema = preview.get("columns")
        schema = schema if isinstance(schema, list) else []
        rows = preview.get("rows")
        rows = rows if isinstance(rows, list) else []
        excluded = {
            "preview", "artifact", "modelArtifact", "resultSummary", "summaryStatus",
            "summaryProvider", "summaryProviderModel", "summaryGeneratedAt",
            "summaryErrorCode",
        }
        information = {
            key: value for key, value in result.items() if key not in excluded
        }
        return to_jsonable_python({
            "requestedLanguage": command.order.requested_language,
            "originalRequest": command.original_request or command.order.request_summary,
            "executionType": command.execution_type,
            "sourceSchema": command.data_schema,
            "approvedOrder": command.order.model_dump(by_alias=True, mode="json"),
            "resultSchema": schema,
            "totalRowCount": total_row_count,
            "resultInformation": information,
            "resultRows": rows if total_row_count <= 100 else None,
        })

    @staticmethod
    def _system_prompt(language: str) -> str:
        output_language = "Turkish" if language == "tr" else "English"
        return (
            "Write a result summary for a non-technical business reader in "
            f"{output_language}. Directly answer originalRequest using only the calculated "
            "result supplied in the user message. Explain the material findings and requested "
            "comparisons in plain business language. For ML results, explain the practical "
            "meaning of the supplied performance indicators and important factors. Do not "
            "invent facts, units, currencies, causes, guarantees, recommendations, or percentage "
            "meanings. Use sourceSchema as the authority for field types, units, currencies, and "
            "categorical meanings. If sourceSchema does not define a unit or currency, do not "
            "name or symbolize one. Return only the summary prose without a heading, JSON, markdown label, "
            "preface, technical implementation details, or repeated interface warnings."
        )

    @staticmethod
    def _json(value: dict[str, Any]) -> str:
        import json
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _clean(text: str) -> str:
        cleaned = re.sub(
            r"^\s*(?:\*\*)?(?:result summary|summary|sonuç özeti|özet)"
            r"(?:\*\*)?\s*:?\s*", "", text, flags=re.IGNORECASE,
        )
        return cleaned.replace("**", "").replace("__", "").strip()
