package io.gulay.entity.data.repository;

import io.gulay.entity.data.model.EntityColumnModel;

import java.util.List;
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

public interface EntityColumnRepository extends JpaRepository<EntityColumnModel, UUID> {
    List<EntityColumnModel> findByEntityIdOrderByOrdinalPosition(UUID entityId);

    Page<EntityColumnModel> findByEntityId(UUID entityId, Pageable pageable);

    boolean existsByEntityId(UUID entityId);
}
