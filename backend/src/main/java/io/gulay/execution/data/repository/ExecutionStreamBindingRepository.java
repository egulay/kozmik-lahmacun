package io.gulay.execution.data.repository;

import io.gulay.execution.data.model.ExecutionStreamBindingModel;

import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ExecutionStreamBindingRepository
        extends JpaRepository<ExecutionStreamBindingModel, UUID> {
}
