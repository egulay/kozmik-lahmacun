package io.gulay.entity.data.repository;

import io.gulay.entity.data.model.BusinessEntityModel;
import io.gulay.entity.data.model.EntityStatus;

import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.Query;

public interface BusinessEntityRepository extends JpaRepository<BusinessEntityModel, UUID> {
    boolean existsByNameIgnoreCase(String name);

    Page<BusinessEntityModel> findByStatus(EntityStatus status, Pageable pageable);

    Page<BusinessEntityModel> findByStatusNot(EntityStatus status, Pageable pageable);

    @Query("select count(distinct c.entity.id) from EntityColumnModel c "
            + "where c.entity.status <> io.gulay.entity.data.model.EntityStatus.DELETION_PENDING")
    long countWithRegisteredSchema();
}
