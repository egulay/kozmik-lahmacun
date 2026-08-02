package io.gulay.execution.data.repository;

import io.gulay.execution.data.model.ExecutionStatusHistoryModel;

import java.util.List;
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ExecutionStatusHistoryRepository
        extends JpaRepository<ExecutionStatusHistoryModel, UUID> {
    List<ExecutionStatusHistoryModel> findByExecutionIdOrderByOccurredAtAsc(UUID executionId);

    List<ExecutionStatusHistoryModel> findByExecutionIdInOrderByOccurredAtAsc(List<UUID> executionIds);
}
