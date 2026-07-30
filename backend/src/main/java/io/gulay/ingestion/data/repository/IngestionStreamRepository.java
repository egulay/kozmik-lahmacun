package io.gulay.ingestion.data.repository;

import io.gulay.ingestion.data.model.IngestionStreamModel;

import java.util.Optional;
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;

public interface IngestionStreamRepository extends JpaRepository<IngestionStreamModel, UUID> {
    Optional<IngestionStreamModel> findFirstByEntityIdOrderByUpdatedAtDesc(UUID entityId);

    Optional<IngestionStreamModel>
    findFirstByEntityIdAndStatusOrderByUpdatedAtDesc(UUID entityId, String status);
}
