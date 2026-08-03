package io.gulay.execution.dto;

import tools.jackson.databind.JsonNode;

import java.util.UUID;

public final class ResultDtos {
    private ResultDtos() {
    }

    public record ArtifactResponse(
            UUID artifactId, String format, String bucket, String objectKey,
            String storageUri) {
    }

    public record ResultResponse(
            String schemaVersion, UUID executionId, long rowCount, JsonNode preview,
            JsonNode kpis, JsonNode charts, JsonNode warnings, ArtifactResponse artifact,
            String guidanceKey, String summaryStatus, String resultSummary,
            int previewPage, int previewSize, long previewTotalElements,
            int previewTotalPages) {
    }
}
