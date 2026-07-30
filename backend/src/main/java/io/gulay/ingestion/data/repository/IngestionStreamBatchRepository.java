package io.gulay.ingestion.data.repository;

import io.gulay.ingestion.data.model.IngestionStreamBatchModel;

import java.util.Optional;
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;

public interface IngestionStreamBatchRepository
        extends JpaRepository<IngestionStreamBatchModel, UUID> {
    Optional<IngestionStreamBatchModel>
    findFirstByStreamIdAndStatusOrderBySequenceNumberDesc(
            UUID streamId, String status);
}
