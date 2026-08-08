package io.gulay.entity.data.repository;

import lombok.RequiredArgsConstructor;
import lombok.val;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.UUID;

@Repository
@RequiredArgsConstructor
public class EntityDeletionRepository {
    private final JdbcClient jdbc;

    @Transactional
    public void prepare(UUID jobId, UUID entityId, UUID actorId, String correlationId, Instant now) {
        val retired = jdbc.sql("""
                update business_entity set status='DELETION_PENDING', updated_at=:now
                where id=:entityId and status <> 'DELETION_PENDING'
                """).param("now", timestamp(now)).param("entityId", entityId).update();
        if (retired != 1) throw new IllegalStateException("Entity is missing or already retired");
        jdbc.sql("""
                insert into deleted_entity_tombstone
                (entity_id, entity_name, schema_snapshot, deleted_by, requested_at, correlation_id)
                select e.id, e.name,
                       coalesce(jsonb_agg(jsonb_build_object(
                           'name', c.column_name, 'type', c.data_type,
                           'ordinalPosition', c.ordinal_position)
                           order by c.ordinal_position) filter (where c.id is not null), '[]'::jsonb),
                       :actorId, :now, :correlationId
                from business_entity e left join entity_column c on c.entity_id=e.id
                where e.id=:entityId group by e.id, e.name
                """).param("actorId", actorId).param("now", timestamp(now))
                .param("correlationId", correlationId).param("entityId", entityId).update();
        jdbc.sql("""
                insert into entity_deletion_job
                (id, entity_id, requested_by, correlation_id, status, attempt_count,
                 requested_at, next_attempt_at)
                values (:id,:entityId,:actorId,:correlationId,'WAITING_FOR_IDLE',0,:now,:now)
                """).param("id", jobId).param("entityId", entityId).param("actorId", actorId)
                .param("correlationId", correlationId).param("now", timestamp(now)).update();
    }

    public List<DeletionJob> findReady(Instant now) {
        return jdbc.sql("""
                select j.id,j.entity_id,j.requested_by,j.correlation_id,u.keycloak_user_id
                from entity_deletion_job j join app_user_reference u on u.id=j.requested_by
                where j.status in ('WAITING_FOR_IDLE','DELETING','RETRY_PENDING')
                  and j.next_attempt_at <= :now order by j.requested_at limit 10
                """).param("now", timestamp(now)).query((row, ignored) -> new DeletionJob(
                        row.getObject("id", UUID.class), row.getObject("entity_id", UUID.class),
                        row.getObject("requested_by", UUID.class), row.getString("keycloak_user_id"),
                        row.getString("correlation_id"))).list();
    }

    public boolean hasActiveWork(UUID entityId) {
        return jdbc.sql("""
                select exists(select 1 from execution_request
                    where entity_id=:id and deleted_at is null
                      and status not in ('SUCCEEDED','FAILED','CANCELLED','TIMED_OUT'))
                or exists(select 1 from import_job where entity_id=:id
                      and status not in ('COMPLETED','FAILED'))
                or exists(select 1 from ingestion_stream_batch b join ingestion_stream s on s.id=b.stream_id
                      where s.entity_id=:id and b.status not in ('COMPLETED','FAILED'))
                """).param("id", entityId).query(Boolean.class).single();
    }

    public List<UUID> terminalExecutions(UUID entityId) {
        return jdbc.sql("""
                select id from execution_request where entity_id=:id and deleted_at is null
                  and status in ('SUCCEEDED','FAILED','CANCELLED','TIMED_OUT')
                """).param("id", entityId).query(UUID.class).list();
    }

    @Transactional
    public boolean claim(UUID jobId, Instant now, Instant leaseUntil) {
        return jdbc.sql("""
                update entity_deletion_job set status='DELETING', next_attempt_at=:lease
                where id=:id and status in ('WAITING_FOR_IDLE','DELETING','RETRY_PENDING')
                  and next_attempt_at <= :now
                """).param("lease", timestamp(leaseUntil)).param("id", jobId)
                .param("now", timestamp(now)).update() == 1;
    }

    @Transactional
    public void waitUntil(UUID jobId, Instant next) {
        jdbc.sql("""
                update entity_deletion_job set status='WAITING_FOR_IDLE',
                next_attempt_at=:next where id=:id
                """).param("next", timestamp(next))
                .param("id", jobId).update();
    }

    @Transactional
    public void retry(UUID jobId, Instant next, String code) {
        jdbc.sql("""
                update entity_deletion_job set status='RETRY_PENDING',
                attempt_count=attempt_count+1,next_attempt_at=:next,last_error_code=:code
                where id=:id
                """).param("next", timestamp(next)).param("code", code)
                .param("id", jobId).update();
    }

    @Transactional
    public void complete(DeletionJob job, Instant now) {
        val id = job.entityId();
        List.of(
                "delete from execution_stream_binding where stream_id in (select id from ingestion_stream where entity_id=:id)",
                "delete from ingestion_stream_event where stream_id in (select id from ingestion_stream where entity_id=:id)",
                "delete from ingestion_stream_batch where stream_id in (select id from ingestion_stream where entity_id=:id)",
                "delete from ingestion_stream where entity_id=:id",
                "delete from import_status_history where import_job_id in (select id from import_job where entity_id=:id)",
                "delete from execution_dataset_binding where import_job_id in (select id from import_job where entity_id=:id)",
                "delete from import_job where entity_id=:id",
                "delete from entity_column where entity_id=:id"
        ).forEach(sql -> jdbc.sql(sql).param("id", id).update());
        jdbc.sql("update deleted_entity_tombstone set deleted_at=:now where entity_id=:id")
                .param("now", timestamp(now)).param("id", id).update();
        jdbc.sql("delete from entity_deletion_job where id=:jobId")
                .param("jobId", job.id()).update();
        jdbc.sql("delete from business_entity where id=:id").param("id", id).update();
    }

    public boolean tombstoned(UUID entityId) {
        return jdbc.sql("select exists(select 1 from deleted_entity_tombstone where entity_id=:id)")
                .param("id", entityId).query(Boolean.class).single();
    }

    private static OffsetDateTime timestamp(Instant value) {
        return OffsetDateTime.ofInstant(value, ZoneOffset.UTC);
    }

    public record DeletionJob(UUID id, UUID entityId, UUID actorId,
                              String actorKeycloakId, String correlationId) {}
}
