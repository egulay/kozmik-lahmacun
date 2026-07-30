package io.gulay.execution.failure.data.repository;

import io.gulay.execution.failure.data.model.ExecutionFailureModel;

import java.util.Optional;
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ExecutionFailureRepository extends JpaRepository<ExecutionFailureModel, UUID> {
    Optional<ExecutionFailureModel> findByExecutionId(UUID executionId);
}
