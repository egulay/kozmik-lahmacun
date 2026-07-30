package io.gulay.audit.data.repository;

import io.gulay.audit.data.model.AuditEventModel;

import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;

public interface AuditEventRepository extends JpaRepository<AuditEventModel, UUID> {
}

