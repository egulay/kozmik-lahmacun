package io.gulay.ingestion.dto;

import java.time.Instant;
import java.util.UUID;

public final class StreamIngestionDtos {
    private StreamIngestionDtos() {
    }

    public record StreamIngestionStatusEvent(
            String schemaVersion, UUID eventId, String correlationId,
            UUID streamId, UUID chunkId, UUID entityId,
            String sourceId, String topic, long sequence, int kafkaPartition,
            long firstOffset, long lastOffset, Instant producedAt, Instant occurredAt,
            String stage, String messageCode, Long batchRowCount,
            Long cumulativeRowCount, String refinedBucket, String refinedObjectKey,
            String errorCode) {
    }
}
