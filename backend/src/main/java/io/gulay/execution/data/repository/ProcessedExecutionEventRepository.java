package io.gulay.execution.data.repository;

import io.gulay.execution.data.model.ProcessedExecutionEventModel;

import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ProcessedExecutionEventRepository
        extends JpaRepository<ProcessedExecutionEventModel, UUID> {
}
