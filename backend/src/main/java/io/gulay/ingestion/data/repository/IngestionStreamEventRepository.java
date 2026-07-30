package io.gulay.ingestion.data.repository;

import io.gulay.ingestion.data.model.IngestionStreamEventModel;

import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;

public interface IngestionStreamEventRepository
        extends JpaRepository<IngestionStreamEventModel, UUID> {
}
