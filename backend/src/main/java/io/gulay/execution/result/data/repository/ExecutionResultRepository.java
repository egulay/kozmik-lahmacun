package io.gulay.execution.result.data.repository;

import io.gulay.execution.result.data.model.ExecutionResultModel;

import java.util.Optional;
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ExecutionResultRepository extends JpaRepository<ExecutionResultModel, UUID> {
    Optional<ExecutionResultModel> findByExecutionId(UUID executionId);
}
