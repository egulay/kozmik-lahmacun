package io.gulay.ingestion.data.repository;

import io.gulay.ingestion.data.model.ImportJobModel;

import java.util.Optional;
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ImportJobRepository extends JpaRepository<ImportJobModel, UUID> {
    Optional<ImportJobModel> findFirstByEntityIdOrderByCreatedAtDesc(UUID entityId);

    Optional<ImportJobModel> findFirstByEntityIdAndStatusOrderByCompletedAtDesc(
            UUID entityId, String status);

    Optional<ImportJobModel>
    findFirstByEntityIdAndStatusAndRefinedBucketIsNotNullAndRefinedObjectKeyIsNotNullOrderByCompletedAtDesc(
            UUID entityId, String status);
}
