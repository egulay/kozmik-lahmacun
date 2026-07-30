package io.gulay.execution.client;

import java.util.List;
import java.util.UUID;

public interface ExecutionArtifactDeletionClient {

    void delete(UUID executionId, String correlationId, List<ArtifactLocation> artifacts);

    record ArtifactLocation(UUID artifactId, String bucket, String objectKey) {
    }
}
