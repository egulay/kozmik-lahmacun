package io.gulay.entity.data.repository;

import io.gulay.entity.data.model.EntityColumnCategoryValueModel;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.UUID;

public interface EntityColumnCategoryValueRepository
        extends JpaRepository<EntityColumnCategoryValueModel, UUID> {
    List<EntityColumnCategoryValueModel> findByColumnIdOrderByValueAsc(UUID columnId);
}
