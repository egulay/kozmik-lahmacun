package io.gulay.execution.data.repository;

import io.gulay.execution.data.model.ExecutionDatasetBindingModel;

import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ExecutionDatasetBindingRepository
        extends JpaRepository<ExecutionDatasetBindingModel, UUID> {
}
