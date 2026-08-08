package io.gulay.entity.client;

import java.util.UUID;

public interface EntityArtifactDeletionClient {
    void delete(UUID entityId, String correlationId);
}
