package io.gulay.ingestion.data.repository;

import io.gulay.ingestion.data.model.ImportJobModel;

import java.util.Optional;
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ImportJobRepository extends JpaRepository<ImportJobModel, UUID> {
    Optional<ImportJobModel> findFirstByEntityIdOrderByCreatedAtDesc(UUID entityId);

    Optional<ImportJobModel> findFirstByEntityIdAndStatusOrderByCompletedAtDesc(
            UUID entityId, String status);

    Optional<ImportJobModel>
    findFirstByEntityIdAndStatusAndRefinedBucketIsNotNullAndRefinedObjectKeyIsNotNullOrderByCompletedAtDesc(
            UUID entityId, String status);

    @Query("select coalesce(sum(job.rowCount), 0) from ImportJobModel job "
            + "where job.entity.id = :entityId and job.status = 'COMPLETED'")
    long completedRows(@Param("entityId") UUID entityId);
}
