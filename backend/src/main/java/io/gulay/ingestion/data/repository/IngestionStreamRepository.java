package io.gulay.ingestion.data.repository;

import io.gulay.ingestion.data.model.IngestionStreamModel;

import java.util.Optional;
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface IngestionStreamRepository extends JpaRepository<IngestionStreamModel, UUID> {
    Optional<IngestionStreamModel> findFirstByEntityIdOrderByUpdatedAtDesc(UUID entityId);

    Optional<IngestionStreamModel>
    findFirstByEntityIdAndLastSequenceIsNotNullAndLastOffsetIsNotNullOrderByUpdatedAtDesc(
            UUID entityId);

    @Query("select coalesce(sum(stream.cumulativeRows), 0) from IngestionStreamModel stream "
            + "where stream.entity.id = :entityId and stream.lastSequence is not null")
    long completedRows(@Param("entityId") UUID entityId);
}
