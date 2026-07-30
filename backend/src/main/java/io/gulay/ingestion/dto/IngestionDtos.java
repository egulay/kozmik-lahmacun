package io.gulay.ingestion.dto;

import java.time.Instant;
import java.util.UUID;

public final class IngestionDtos {
    private IngestionDtos() {
    }

    public record ImportStatusEvent(
            String schemaVersion, UUID eventId, String correlationId, UUID importId,
            UUID sourceEventId, UUID entityId, Instant occurredAt,
            String sourceType, String sourceReference, String stage, String status,
            String messageCode,
            Long rowCount, String refinedBucket, String refinedObjectKey,
            String errorCode, String errorMessage) {
    }
}
