package io.gulay.execution.messaging;

import tools.jackson.databind.JsonNode;

import java.time.Instant;
import java.util.UUID;

public final class ExecutionMessagingContracts {
    private ExecutionMessagingContracts() {
    }

    public record ExecutionCommand(
            String schemaVersion, UUID eventId, String correlationId, UUID executionId,
            UUID entityId, UUID actorUserId, Instant occurredAt, String executionType,
            JsonNode order, JsonNode authorization, JsonNode configuration) {
    }

    public record ExecutionStatusEvent(
            String schemaVersion, UUID eventId, String correlationId, UUID executionId,
            UUID entityId, UUID actorUserId, Instant occurredAt, String stage, String status,
            int progressPercent, String messageCode, JsonNode details) {
    }

    public record ExecutionControlCommand(
            String schemaVersion, UUID eventId, String correlationId, UUID executionId,
            UUID entityId, UUID actorUserId, Instant occurredAt, String operation) {
    }

    public record ArtifactRetentionCommand(
            String schemaVersion, UUID eventId, String correlationId, UUID executionId,
            UUID entityId, UUID actorUserId, Instant occurredAt, String operation,
            UUID artifactId, String bucket, String objectKey) {
    }

    public record ArtifactRetentionEvent(
            String schemaVersion, UUID eventId, String correlationId, UUID executionId,
            UUID entityId, UUID actorUserId, Instant occurredAt, String operation,
            UUID artifactId, String bucket, String objectKey, String status,
            String resultCode) {
    }

    public record ExecutionResultNotification(
            String schemaVersion, UUID eventId, String correlationId, UUID executionId,
            UUID entityId, UUID actorUserId, Instant occurredAt, String status,
            String resultCode, long rowCount, JsonNode preview, JsonNode kpis,
            JsonNode charts, JsonNode warnings, Artifact artifact,
            Artifact modelArtifact, String summaryStatus, String managementSummary) {
    }

    public record Artifact(
            UUID artifactId, String format, String bucket, String objectKey, Long sizeBytes) {
    }
}
