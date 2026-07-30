package io.gulay.retention.data.repository;

import lombok.RequiredArgsConstructor;
import lombok.val;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

@Repository
@RequiredArgsConstructor
public class RetentionPurgeRepository {

    private static final int BATCH_SIZE = 100;

    private final JdbcTemplate jdbc;

    @Transactional
    public int purgeConfirmedDeletedArtifacts(Instant cutoff) {
        return jdbc.update("""
                delete from execution_artifact
                where id in (
                    select id
                    from execution_artifact
                    where deleted_at < ?
                    order by deleted_at
                    limit ?
                )
                """, cutoff, BATCH_SIZE);
    }

    @Transactional
    public int purgeSoftDeletedExecutions(Instant cutoff) {
        val ids = jdbc.queryForList("""
                select e.id
                from execution_request e
                where e.deleted_at < ?
                  and not exists (
                      select 1
                      from execution_result r
                      join execution_artifact a on a.execution_result_id = r.id
                      where r.execution_id = e.id
                        and a.deleted_at is null
                  )
                order by e.deleted_at
                limit ?
                """, UUID.class, cutoff, BATCH_SIZE);
        return ids.stream().mapToInt(this::deleteExecutionGraph).sum();
    }

    @Transactional
    public int purgeSoftDeletedUsers(Instant cutoff) {
        val ids = jdbc.queryForList("""
                select u.id
                from app_user_reference u
                where u.deleted_at < ?
                  and not exists (
                      select 1 from execution_request e where e.owner_user_id = u.id
                  )
                  and not exists (
                      select 1
                      from execution_deletion_job d
                      where d.requested_by = u.id and d.status <> 'COMPLETED'
                  )
                  and not exists (
                      select 1
                      from user_management_operation o
                      where (o.target_user_id = u.id or o.actor_user_id = u.id)
                        and o.status <> 'COMPLETED'
                  )
                order by u.deleted_at
                limit ?
                """, UUID.class, cutoff, BATCH_SIZE);
        return ids.stream().mapToInt(this::deleteUserTombstone).sum();
    }

    private int deleteExecutionGraph(UUID executionId) {
        val statements = List.of(
                "delete from execution_failure where execution_id = ?",
                "delete from processed_execution_event where execution_id = ?",
                "delete from execution_status_history where execution_id = ?",
                "delete from execution_dataset_binding where execution_id = ?",
                "delete from execution_stream_binding where execution_id = ?",
                """
                        delete from execution_artifact
                        where execution_result_id in (
                            select id from execution_result where execution_id = ?
                        )
                        """,
                "delete from execution_result where execution_id = ?",
                "delete from execution_command_outbox where execution_id = ?",
                "delete from execution_request where id = ?"
        );
        statements.subList(0, statements.size() - 1)
                .forEach(statement -> jdbc.update(statement, executionId));
        return jdbc.update(statements.get(statements.size() - 1), executionId);
    }

    private int deleteUserTombstone(UUID userId) {
        jdbc.update("update audit_event set actor_user_id = null where actor_user_id = ?", userId);
        jdbc.update("update business_entity set created_by = null where created_by = ?", userId);
        jdbc.update("delete from chat_thread where owner_user_id = ?", userId);
        jdbc.update("""
                delete from user_management_operation
                where (target_user_id = ? or actor_user_id = ?)
                  and status = 'COMPLETED'
                """, userId, userId);
        jdbc.update("""
                delete from execution_deletion_job
                where requested_by = ? and status = 'COMPLETED'
                """, userId);
        return jdbc.update(
                "delete from app_user_reference where id = ? and deleted_at is not null",
                userId);
    }
}
