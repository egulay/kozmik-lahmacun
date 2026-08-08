package io.gulay.ingestion;

import lombok.val;

import tools.jackson.databind.ObjectMapper;
import io.gulay.entity.data.repository.BusinessEntityRepository;
import io.gulay.entity.data.model.EntityStatus;
import io.gulay.execution.messaging.KafkaMessageSigner;
import io.gulay.ingestion.data.model.IngestionStreamBatchModel;
import io.gulay.ingestion.data.model.IngestionStreamEventModel;
import io.gulay.ingestion.data.model.IngestionStreamModel;
import io.gulay.ingestion.data.repository.IngestionStreamBatchRepository;
import io.gulay.ingestion.data.repository.IngestionStreamEventRepository;
import io.gulay.ingestion.data.repository.IngestionStreamRepository;
import io.gulay.ingestion.dto.StreamIngestionDtos;

import java.time.Clock;
import java.time.Instant;
import java.util.Set;

import lombok.RequiredArgsConstructor;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Component
@RequiredArgsConstructor
public class StreamIngestionEventConsumer {
    private static final Set<String> STAGES =
            Set.of("RECEIVED", "VALIDATING", "RUNNING", "WRITING_RESULTS", "COMPLETED", "FAILED");
    private final ObjectMapper mapper;
    private final KafkaMessageSigner signer;
    private final IngestionStreamRepository streams;
    private final IngestionStreamBatchRepository batches;
    private final IngestionStreamEventRepository events;
    private final BusinessEntityRepository entities;
    private final IngestionEventHub eventHub;
    private final Clock clock;

    @KafkaListener(topics =
            "${kozmik.kafka.stream-status-topic:ingestion.stream.status.v1}")
    @Transactional
    public void consume(String payload) {
        apply(mapper.readValue(
                signer.unwrap(payload), StreamIngestionDtos.StreamIngestionStatusEvent.class));
    }

    @Transactional
    public void apply(StreamIngestionDtos.StreamIngestionStatusEvent event) {
        validate(event);
        if (events.existsById(event.eventId())) return;
        val now = Instant.now(clock);
        val stream = streams.findById(event.streamId()).orElseGet(() ->
                streams.save(IngestionStreamModel.builder()
                        .id(event.streamId())
                        .entity(entities.findById(event.entityId())
                                .filter(entity -> entity.getStatus() == EntityStatus.ACTIVE).orElseThrow(
                                () -> new IllegalArgumentException("Unknown entity")))
                        .sourceId(event.sourceId()).topic(event.topic()).status("ACTIVE")
                        .cumulativeRows(0).startedAt(now).updatedAt(now).build()));
        if (!stream.getEntity().getId().equals(event.entityId())
                || !stream.getSourceId().equals(event.sourceId())
                || !stream.getTopic().equals(event.topic())) {
            throw new IllegalArgumentException("Stream identity binding mismatch");
        }
        val existingBatch = batches.findById(event.chunkId());
        if (existingBatch.isEmpty()
                && stream.getEntity().getStatus() != EntityStatus.ACTIVE) {
            throw new IllegalArgumentException("Entity UUID is retired for new stream chunks");
        }
        val batch = existingBatch.orElseGet(() ->
                batches.save(IngestionStreamBatchModel.builder()
                        .chunkId(event.chunkId()).stream(stream)
                        .sequenceNumber(event.sequence())
                        .kafkaPartition(event.kafkaPartition())
                        .firstOffset(event.firstOffset()).lastOffset(event.lastOffset())
                        .producedAt(event.producedAt()).status("RECEIVED")
                        .createdAt(now).build()));
        if (!batch.getStream().getId().equals(event.streamId())
                || batch.getSequenceNumber() != event.sequence()
                || batch.getKafkaPartition() != event.kafkaPartition()
                || batch.getFirstOffset() != event.firstOffset()) {
            throw new IllegalArgumentException("Stream batch identity binding mismatch");
        }
        if ("COMPLETED".equals(event.stage())) {
            if (event.batchRowCount() == null || event.cumulativeRowCount() == null) {
                throw new IllegalArgumentException("Incomplete stream checkpoint");
            }
            batch.complete(event.batchRowCount(), event.refinedBucket(),
                    event.refinedObjectKey(), event.occurredAt());
            stream.checkpoint(event.cumulativeRowCount(), event.sequence(),
                    event.kafkaPartition(), event.lastOffset(), event.occurredAt());
        } else if ("FAILED".equals(event.stage())) {
            batch.fail(event.errorCode(), event.occurredAt());
            stream.recordFailure(event.errorCode(), event.occurredAt());
        } else {
            stream.markIngesting(event.occurredAt());
        }
        events.save(IngestionStreamEventModel.builder()
                .eventId(event.eventId()).stream(stream).chunkId(event.chunkId())
                .stage(event.stage()).messageCode(event.messageCode())
                .occurredAt(event.occurredAt()).build());
        afterCommit(new IngestionEventHub.IngestionUiEvent(
                "1.0", event.eventId(), event.entityId(),
                "FAILED".equals(event.stage()) ? "ingestion-failed"
                        : "COMPLETED".equals(event.stage())
                        ? "ingestion-completed" : "ingestion-stage-changed",
                "STREAM", event.stage(),
                "FAILED".equals(event.stage()) ? "FAILED"
                        : "COMPLETED".equals(event.stage()) ? "COMPLETED" : "INGESTING",
                event.messageCode(), event.batchRowCount(),
                event.cumulativeRowCount(), event.occurredAt()));
    }

    private void afterCommit(IngestionEventHub.IngestionUiEvent event) {
        TransactionSynchronizationManager.registerSynchronization(
                new TransactionSynchronization() {
                    @Override
                    public void afterCommit() {
                        eventHub.publish(event);
                    }
                });
    }

    private void validate(StreamIngestionDtos.StreamIngestionStatusEvent event) {
        val expectedPrefix = "entities/" + event.entityId() + "/dataset/part-stream-"
                + event.streamId() + "-";
        if (!"1.0".equals(event.schemaVersion()) || event.eventId() == null
                || event.streamId() == null || event.chunkId() == null
                || event.entityId() == null || event.correlationId() == null
                || event.sourceId() == null || event.sourceId().isBlank()
                || !"ingestion.records.v1".equals(event.topic())
                || event.sequence() < 0 || event.kafkaPartition() < 0
                || event.firstOffset() < 0 || event.lastOffset() < event.firstOffset()
                || event.producedAt() == null || event.occurredAt() == null
                || !STAGES.contains(event.stage())
                || event.refinedObjectKey() != null
                && (!event.refinedObjectKey().startsWith(expectedPrefix)
                || !event.refinedObjectKey().endsWith(".parquet"))) {
            throw new IllegalArgumentException("Unsafe CDR stream status event");
        }
    }
}
