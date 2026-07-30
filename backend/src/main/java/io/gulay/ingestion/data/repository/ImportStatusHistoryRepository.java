package io.gulay.ingestion.data.repository;

import io.gulay.ingestion.data.model.ImportStatusHistoryModel;

import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ImportStatusHistoryRepository extends JpaRepository<ImportStatusHistoryModel, UUID> {
    boolean existsByEventId(UUID eventId);
}
