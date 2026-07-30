package io.gulay.execution.dto;

import tools.jackson.databind.JsonNode;

import java.util.UUID;

public final class GovernedDatasetDtos {
    private GovernedDatasetDtos() {
    }

    public record GovernedDatasetResponse(
            String schemaVersion,
            UUID executionId,
            UUID entityId,
            UUID importId,
            UUID streamId,
            Long throughSequence,
            String format,
            String bucket,
            String objectKey,
            long rowCount,
            String executionType,
            UUID actorUserId,
            JsonNode executionOrder,
            JsonNode authorizationSnapshot,
            JsonNode configurationSnapshot) {
    }
}
