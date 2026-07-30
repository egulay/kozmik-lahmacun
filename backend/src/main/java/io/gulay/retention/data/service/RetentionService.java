package io.gulay.retention.data.service;

import lombok.val;

import io.gulay.audit.data.model.AuditOutcome;
import io.gulay.audit.data.service.AuditEventService;
import io.gulay.execution.messaging.ExecutionMessagingContracts;
import io.gulay.execution.messaging.KafkaMessageSigner;
import io.gulay.retention.data.repository.RetentionPurgeRepository;
import tools.jackson.databind.ObjectMapper;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.UUID;
import java.util.function.IntSupplier;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
@RequiredArgsConstructor
@Slf4j
public class RetentionService {
    private final JdbcTemplate jdbc;
    private final AuditEventService audit;
    private final Clock clock;
    private final KafkaTemplate<String, String> kafka;
    private final KafkaMessageSigner signer;
    private final ObjectMapper objectMapper;
    private final RetentionPurgeRepository purgeRepository;
    private final TransactionTemplate transactions;

    @Value("${kozmik.kafka.control-topic:execution.control.v1}")
    private String controlTopic;
    @Value("${kozmik.retention.chat-days:30}")
    private long chatDays;
    @Value("${kozmik.retention.preview-days:30}")
    private long previewDays;
    @Value("${kozmik.retention.artifact-days:90}")
    private long artifactDays;
    @Value("${kozmik.retention.execution-days:90}")
    private long executionDays;
    @Value("${kozmik.retention.hard-delete-days:30}")
    private long hardDeleteDays;

    @Scheduled(cron = "${kozmik.retention.cron:0 17 2 * * *}")
    public void run() {
        val runId = UUID.randomUUID().toString();
        val now = Instant.now(clock);
        try {
            inTransaction(() -> purgeChats(
                    now.minus(Duration.ofDays(validDays(chatDays, 30)))));
            inTransaction(() -> redactPreviews(
                    now.minus(Duration.ofDays(validDays(previewDays, 30)))));
            removeArtifacts(now.minus(Duration.ofDays(validDays(artifactDays, 90))));
            inTransaction(() -> retireExecutions(
                    now.minus(Duration.ofDays(validDays(executionDays, 90)))));
            audit.record("RETENTION_RUN", null, "RETENTION", runId, runId,
                    AuditOutcome.SUCCEEDED, "RETENTION_COMPLETED");
        } catch (Exception exception) {
            audit.record("RETENTION_RUN", null, "RETENTION", runId, runId,
                    AuditOutcome.FAILED, "RETENTION_PARTIAL_FAILURE");
        }
    }

    @Scheduled(cron = "${kozmik.retention.hard-delete-cron:0 0 0 * * *}")
    public void hardDeleteSoftDeletedData() {
        val runId = UUID.randomUUID().toString();
        val cutoff = Instant.now(clock).minus(
                Duration.ofDays(validDays(hardDeleteDays, 30)));
        try {
            val artifactCount = purgeAll(
                    () -> purgeRepository.purgeConfirmedDeletedArtifacts(cutoff));
            val executionCount = purgeAll(
                    () -> purgeRepository.purgeSoftDeletedExecutions(cutoff));
            val userCount = purgeAll(
                    () -> purgeRepository.purgeSoftDeletedUsers(cutoff));
            audit.record("HARD_DELETE_RETENTION_RUN", null, "RETENTION", runId, runId,
                    AuditOutcome.SUCCEEDED, "HARD_DELETE_RETENTION_COMPLETED");
            log.info(
                    "hard_delete_retention_completed runId={} cutoff={} artifacts={} "
                            + "executions={} users={}",
                    runId, cutoff, artifactCount, executionCount, userCount);
        } catch (RuntimeException exception) {
            audit.record("HARD_DELETE_RETENTION_RUN", null, "RETENTION", runId, runId,
                    AuditOutcome.FAILED, "HARD_DELETE_RETENTION_FAILED");
            log.error(
                    "hard_delete_retention_failed runId={} cutoff={} code=HARD_DELETE_FAILED",
                    runId, cutoff, exception);
        }
    }

    private int purgeChats(Instant cutoff) {
        // Messages are aggregate children and PostgreSQL removes them through
        // fk_chat_message_thread ON DELETE CASCADE.
        return jdbc.update("""
                delete from chat_thread
                where created_at < ?
                """, cutoff);
    }

    private int redactPreviews(Instant cutoff) {
        return jdbc.update("""
                update execution_result
                set preview_json='{"retained":false,"rows":[]}'::jsonb, preview_deleted_at=now()
                where preview_deleted_at is null and created_at < ?
                """, cutoff);
    }

    public void removeArtifacts(Instant cutoff) {
        val rows = jdbc.query("""
                select a.id, a.bucket_name, a.object_key, e.id execution_id,
                       e.entity_id, e.owner_user_id, e.correlation_id
                from execution_artifact a
                join execution_result r on r.id=a.execution_result_id
                join execution_request e on e.id=r.execution_id
                where a.deleted_at is null and a.created_at < ?
                """, (result, row) -> new ArtifactRow(
                result.getObject("id", UUID.class), result.getString("bucket_name"),
                result.getString("object_key"),
                result.getObject("execution_id", UUID.class),
                result.getObject("entity_id", UUID.class),
                result.getObject("owner_user_id", UUID.class),
                result.getString("correlation_id")), cutoff);
        for (val row : rows) {
            try {
                val command = new ExecutionMessagingContracts.ArtifactRetentionCommand(
                        "1.0", UUID.randomUUID(), row.correlationId(), row.executionId(),
                        row.entityId(), row.actorUserId(), Instant.now(clock),
                        "DELETE_ARTIFACT", row.id(), row.bucket(), row.objectKey());
                kafka.send(controlTopic, row.executionId().toString(),
                        signer.wrap(objectMapper.writeValueAsString(command)));
            } catch (Exception exception) {
                jdbc.update("""
                        update execution_artifact set deletion_error_code='DELETE_COMMAND_FAILED'
                        where id=?
                        """, row.id());
            }
        }
    }

    private int retireExecutions(Instant cutoff) {
        return jdbc.update("""
                update execution_request set deleted_at=now()
                where deleted_at is null and completed_at is not null and completed_at < ?
                """, cutoff);
    }

    private long validDays(long value, long fallback) {
        return value > 0 && value <= 3650 ? value : fallback;
    }

    private int inTransaction(IntSupplier operation) {
        val result = transactions.execute(status -> operation.getAsInt());
        return result == null ? 0 : result;
    }

    private int purgeAll(PurgeBatch batch) {
        var total = 0;
        int purged;
        do {
            purged = batch.run();
            total += purged;
        } while (purged > 0);
        return total;
    }

    @FunctionalInterface
    private interface PurgeBatch {
        int run();
    }

    private record ArtifactRow(
            UUID id, String bucket, String objectKey, UUID executionId, UUID entityId,
            UUID actorUserId, String correlationId) {
    }
}
