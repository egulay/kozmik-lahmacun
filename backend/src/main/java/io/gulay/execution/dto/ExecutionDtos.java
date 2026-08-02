package io.gulay.execution.dto;

import tools.jackson.databind.JsonNode;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

public final class ExecutionDtos {
    public static final String SCHEMA_VERSION = "1.0";

    private ExecutionDtos() {
    }

    public record CreateReportPlanRequest(
            @NotNull UUID entityId,
            @NotBlank @Size(max = 4000) String request,
            @NotBlank @Pattern(regexp = "^[a-z]{2}(-[A-Z]{2})?$") String language) {
    }

    public record ReportPlanResponse(
            String schemaVersion, UUID id, String executionType, String status,
            UUID entityId, Instant requestedAt, JsonNode order) {
    }

    public record StatusHistoryResponse(
            UUID eventId, String stage, String status, int progressPercent,
            String messageCode, JsonNode details, Instant occurredAt) {
    }

    public record ExecutionFailureResponse(
            String schemaVersion, String failureCode, String failedStage,
            String sanitizedTechnicalReason, String userExplanation,
            String explanationStatus, boolean retryable, String language,
            Instant createdAt) {
    }

    public record ExecutionStateResponse(
            String schemaVersion, UUID id, String executionType, String status,
            UUID entityId, String entityName, String requester, String originalRequest,
            Instant requestedAt, Instant startedAt,
            Instant completedAt, JsonNode order, List<StatusHistoryResponse> history,
            ExecutionFailureResponse failure) {
    }

    public record ExecutionSummaryResponse(
            UUID id, String executionType, String status, UUID entityId,
            String entityName, String entityNameTr, String requester,
            String originalRequest, Instant requestedAt,
            Instant startedAt, Instant completedAt, String latestStage,
            Integer latestProgressPercent) {
    }

    public record ExecutionListResponse(
            String schemaVersion, List<ExecutionSummaryResponse> executions,
            int page, int size, long totalElements, int totalPages,
            boolean first, boolean last) {
    }

    public record ExecutionDeletionResponse(
            String schemaVersion, UUID executionId, String status) {
    }
}
