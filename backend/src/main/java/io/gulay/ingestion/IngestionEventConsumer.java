package io.gulay.ingestion;

import lombok.val;

import tools.jackson.databind.ObjectMapper;
import io.gulay.entity.data.repository.BusinessEntityRepository;
import io.gulay.entity.data.model.EntityStatus;
import io.gulay.ingestion.data.model.ImportJobModel;
import io.gulay.ingestion.data.model.ImportStatusHistoryModel;
import io.gulay.ingestion.data.repository.ImportJobRepository;
import io.gulay.ingestion.data.repository.ImportStatusHistoryRepository;
import io.gulay.ingestion.dto.IngestionDtos;
import io.gulay.execution.messaging.KafkaMessageSigner;

import java.time.Clock;
import java.time.Instant;
import java.util.Set;
import java.util.UUID;

import lombok.RequiredArgsConstructor;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Component
@RequiredArgsConstructor
public class IngestionEventConsumer {
    private static final Set<String> STAGES =
            Set.of("RECEIVED", "VALIDATING", "RUNNING", "WRITING_RESULTS", "COMPLETED", "FAILED");
    private static final Set<String> CODES = Set.of(
            "IMPORT_RECEIVED", "IMPORT_VALIDATING", "IMPORT_SPARK_RUNNING",
            "IMPORT_WRITING_REFINED", "IMPORT_COMPLETED", "UNKNOWN_ENTITY",
            "INVALID_FILENAME", "SCHEMA_MISMATCH", "IMPORT_FAILED", "ARTIFACT_WRITE_FAILED");
    private static final Set<String> SOURCE_TYPES = Set.of("MINIO_OBJECT_CREATED");
    private final ObjectMapper mapper;
    private final KafkaMessageSigner signer;
    private final ImportJobRepository jobs;
    private final ImportStatusHistoryRepository history;
    private final BusinessEntityRepository entities;
    private final IngestionEventHub eventHub;
    private final Clock clock;

    @KafkaListener(topics = "${kozmik.kafka.ingestion-status-topic:ingestion.status.v1}")
    @Transactional
    public void consume(String payload) {
        apply(mapper.readValue(signer.unwrap(payload), IngestionDtos.ImportStatusEvent.class));
    }

    @Transactional
    public void apply(IngestionDtos.ImportStatusEvent event) {
        if (!"1.0".equals(event.schemaVersion()) || event.eventId() == null
                || event.importId() == null || event.sourceEventId() == null
                || event.entityId() == null || event.correlationId() == null
                || event.correlationId().isBlank() || !STAGES.contains(event.stage())
                || !CODES.contains(event.messageCode())
                || !SOURCE_TYPES.contains(event.sourceType())
                || event.sourceReference() == null || event.sourceReference().length() > 1200
                || event.errorMessage() != null && event.errorMessage().length() > 1000
                || event.refinedObjectKey() != null && !event.refinedObjectKey().matches(
                "^entities/" + event.entityId()
                        + "/dataset/part-file-[A-Za-z0-9-]{36}\\.parquet$")) {
            throw new IllegalArgumentException("Unsafe ingestion status event");
        }
        if (history.existsByEventId(event.eventId())) return;
        val existingJob = jobs.findById(event.importId());
        val job = existingJob.orElseGet(() -> jobs.save(ImportJobModel.builder()
                .id(event.importId()).sourceEventId(event.sourceEventId())
                .entity(entities.findById(event.entityId()).filter(
                                entity -> entity.getStatus() == EntityStatus.ACTIVE)
                        .orElseThrow(() -> new IllegalArgumentException("Unknown entity")))
                .sourceType(event.sourceType()).sourceReference(event.sourceReference())
                .status("RECEIVED").createdAt(Instant.now(clock)).build()));
        if (!job.getSourceEventId().equals(event.sourceEventId())
                || !job.getEntity().getId().equals(event.entityId())
                || !job.getSourceType().equals(event.sourceType())) {
            throw new IllegalArgumentException("Import identity binding mismatch");
        }
        job.apply(event.status(), event.occurredAt(), event.rowCount(),
                event.refinedBucket(), event.refinedObjectKey(),
                event.errorCode(), event.errorMessage());
        history.save(ImportStatusHistoryModel.builder().id(UUID.randomUUID()).eventId(event.eventId())
                .importJob(job).stage(event.stage()).status(event.status())
                .messageCode(event.messageCode()).occurredAt(event.occurredAt()).build());
        afterCommit(new IngestionEventHub.IngestionUiEvent(
                "1.0", event.eventId(), event.entityId(),
                "FAILED".equals(event.stage()) ? "ingestion-failed"
                        : "COMPLETED".equals(event.stage()) ? "ingestion-completed"
                        : "ingestion-stage-changed",
                "FILE", event.stage(), event.status(), event.messageCode(),
                event.rowCount(), event.rowCount(), event.occurredAt()));
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
}
