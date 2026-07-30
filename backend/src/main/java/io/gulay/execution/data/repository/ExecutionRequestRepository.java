package io.gulay.execution.data.repository;

import io.gulay.execution.data.model.ExecutionRequestModel;

import java.time.Instant;
import java.util.List;
import java.util.Set;
import java.util.Optional;
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Page;
import org.springframework.data.jpa.repository.Query;

public interface ExecutionRequestRepository extends JpaRepository<ExecutionRequestModel, UUID> {
    Optional<ExecutionRequestModel> findByOwnerIdAndIdempotencyKey(UUID ownerId, String idempotencyKey);

    Optional<ExecutionRequestModel> findByIdAndOwnerKeycloakUserId(UUID id, String keycloakUserId);

    @Query("""
            select e from ExecutionRequestModel e
            where e.owner.keycloakUserId = :keycloakUserId
              and e.deletedAt is null
              and e.status in :statuses
              and (
                :search = ''
                or lower(e.entity.name) like lower(concat('%', :search, '%'))
                or lower(e.executionType) like lower(concat('%', :search, '%'))
                or lower(e.owner.displayName) like lower(concat('%', :search, '%'))
                or lower(e.originalRequest) like lower(concat('%', :search, '%'))
              )
            """)
    Page<ExecutionRequestModel> findVisiblePage(
            String keycloakUserId, Set<io.gulay.execution.data.model.ExecutionStatus> statuses,
            String search, Pageable pageable);

    @Query("""
            select e from ExecutionRequestModel e
            where e.deletedAt is null
              and e.status in :statuses
              and (
                :search = ''
                or lower(e.entity.name) like lower(concat('%', :search, '%'))
                or lower(e.executionType) like lower(concat('%', :search, '%'))
                or lower(e.owner.displayName) like lower(concat('%', :search, '%'))
                or lower(e.originalRequest) like lower(concat('%', :search, '%'))
              )
            """)
    Page<ExecutionRequestModel> findAdminPage(
            Set<io.gulay.execution.data.model.ExecutionStatus> statuses,
            String search, Pageable pageable);

    @org.springframework.data.jpa.repository.Query("""
            select e from ExecutionRequestModel e
            where e.completedAt is null and e.timeoutAt is not null and e.timeoutAt <= :now
            """)
    List<ExecutionRequestModel> findOverdue(Instant now);
}
