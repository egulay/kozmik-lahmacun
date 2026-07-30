package io.gulay.execution.data.repository;

import lombok.val;

import io.gulay.execution.client.ExecutionArtifactDeletionClient.ArtifactLocation;

import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.UUID;

import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
@RequiredArgsConstructor
public class ExecutionDeletionRepository {

    private final JdbcClient jdbc;

    public List<ArtifactLocation> findExecutionArtifacts(UUID executionId) {
        return jdbc.sql("""
                        select a.id, a.bucket_name, a.object_key
                        from execution_artifact a
                        join execution_result r on r.id = a.execution_result_id
                        where r.execution_id = :executionId
                          and a.deleted_at is null
                        order by a.id
                        """)
                .param("executionId", executionId)
                .query((row, ignored) -> new ArtifactLocation(
                        row.getObject("id", UUID.class),
                        row.getString("bucket_name"),
                        row.getString("object_key")))
                .list();
    }

    @Transactional
    public void prepare(
            UUID jobId,
            UUID executionId,
            UUID actorId,
            String correlationId,
            String actorRole,
            Instant now,
            List<ArtifactLocation> artifacts) {
        val hidden = jdbc.sql("""
                        update execution_request
                        set deleted_at = :now
                        where id = :executionId
                          and deleted_at is null
                          and status in ('SUCCEEDED', 'FAILED', 'CANCELLED', 'TIMED_OUT')
                        """)
                .param("now", timestamp(now))
                .param("executionId", executionId)
                .update();
        if (hidden != 1) {
            throw new IllegalStateException("Execution deletion could not be prepared");
        }
        jdbc.sql("""
                        insert into execution_deletion_job
                        (id, execution_id, requested_by, correlation_id, actor_role, status,
                         attempt_count, requested_at, next_attempt_at)
                        values (:id, :executionId, :actorId, :correlationId, :actorRole,
                                'PENDING', 0, :now, :now)
                        """)
                .param("id", jobId)
                .param("executionId", executionId)
                .param("actorId", actorId)
                .param("correlationId", correlationId)
                .param("actorRole", actorRole)
                .param("now", timestamp(now))
                .update();
        artifacts.forEach(artifact -> jdbc.sql("""
                        insert into execution_deletion_artifact
                        (id, deletion_job_id, artifact_id, bucket_name, object_key)
                        values (:id, :jobId, :artifactId, :bucket, :objectKey)
                        """)
                .param("id", UUID.randomUUID())
                .param("jobId", jobId)
                .param("artifactId", artifact.artifactId())
                .param("bucket", artifact.bucket())
                .param("objectKey", artifact.objectKey())
                .update());
    }

    public List<DeletionJob> findReady(Instant now) {
        return jdbc.sql("""
                        select id, execution_id, requested_by, correlation_id, actor_role
                        from execution_deletion_job
                        where status in ('PENDING', 'PROCESSING', 'RETRY_PENDING')
                          and next_attempt_at <= :now
                        order by requested_at
                        limit 20
                        """)
                .param("now", timestamp(now))
                .query((row, ignored) -> new DeletionJob(
                        row.getObject("id", UUID.class),
                        row.getObject("execution_id", UUID.class),
                        row.getObject("requested_by", UUID.class),
                        row.getString("correlation_id"),
                        row.getString("actor_role")))
                .list();
    }

    public List<ArtifactLocation> findJobArtifacts(UUID jobId) {
        return jdbc.sql("""
                        select artifact_id, bucket_name, object_key
                        from execution_deletion_artifact
                        where deletion_job_id = :jobId
                        order by artifact_id
                        """)
                .param("jobId", jobId)
                .query((row, ignored) -> new ArtifactLocation(
                        row.getObject("artifact_id", UUID.class),
                        row.getString("bucket_name"),
                        row.getString("object_key")))
                .list();
    }

    @Transactional
    public boolean claim(UUID jobId, Instant claimAt, Instant leaseUntil) {
        return jdbc.sql("""
                        update execution_deletion_job
                        set status='PROCESSING', next_attempt_at=:leaseUntil
                        where id=:id
                          and status in ('PENDING', 'PROCESSING', 'RETRY_PENDING')
                          and next_attempt_at <= :claimAt
                        """)
                .param("claimAt", timestamp(claimAt))
                .param("leaseUntil", timestamp(leaseUntil))
                .param("id", jobId)
                .update() == 1;
    }

    @Transactional
    public void complete(DeletionJob job, Instant now) {
        deleteGraph(job.executionId());
        jdbc.sql("""
                        update execution_deletion_job
                        set status='COMPLETED', completed_at=:now, next_attempt_at=:now,
                            attempt_count=attempt_count + 1, last_error_code=null
                        where id=:id and status='PROCESSING'
                        """)
                .param("now", timestamp(now))
                .param("id", job.id())
                .update();
    }

    @Transactional
    public void retryLater(UUID jobId, Instant nextAttemptAt) {
        jdbc.sql("""
                        update execution_deletion_job
                        set status='RETRY_PENDING', attempt_count=attempt_count + 1,
                            next_attempt_at=:nextAttemptAt,
                            last_error_code='ARTIFACT_DELETE_FAILED'
                        where id=:id and status='PROCESSING'
                        """)
                .param("nextAttemptAt", timestamp(nextAttemptAt))
                .param("id", jobId)
                .update();
    }

    private void deleteGraph(UUID executionId) {
        List.of(
                "delete from execution_failure where execution_id = :executionId",
                "delete from processed_execution_event where execution_id = :executionId",
                "delete from execution_status_history where execution_id = :executionId",
                "delete from execution_dataset_binding where execution_id = :executionId",
                "delete from execution_stream_binding where execution_id = :executionId",
                """
                        delete from execution_artifact
                        where execution_result_id in (
                            select id from execution_result where execution_id = :executionId
                        )
                        """,
                "delete from execution_result where execution_id = :executionId",
                "delete from execution_command_outbox where execution_id = :executionId",
                "delete from execution_request where id = :executionId"
        ).forEach(statement -> jdbc.sql(statement)
                .param("executionId", executionId)
                .update());
    }

    private static OffsetDateTime timestamp(Instant instant) {
        return OffsetDateTime.ofInstant(instant, ZoneOffset.UTC);
    }

    public record DeletionJob(
            UUID id,
            UUID executionId,
            UUID actorId,
            String correlationId,
            String actorRole) {
    }
}
