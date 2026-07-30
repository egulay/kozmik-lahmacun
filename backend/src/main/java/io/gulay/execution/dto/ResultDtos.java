package io.gulay.execution.dto;

import tools.jackson.databind.JsonNode;

import java.util.UUID;

public final class ResultDtos {
    private ResultDtos() {
    }

    public record ArtifactResponse(
            UUID artifactId, String format) {
    }

    public record ResultResponse(
            String schemaVersion, UUID executionId, long rowCount, JsonNode preview,
            JsonNode kpis, JsonNode charts, JsonNode warnings, ArtifactResponse artifact,
            String guidanceKey, String summaryStatus, String managementSummary) {
    }
}
