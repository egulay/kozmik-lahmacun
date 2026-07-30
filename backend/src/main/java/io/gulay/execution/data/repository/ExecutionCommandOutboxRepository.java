package io.gulay.execution.data.repository;

import io.gulay.execution.data.model.ExecutionCommandOutboxModel;

import java.util.List;
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ExecutionCommandOutboxRepository
        extends JpaRepository<ExecutionCommandOutboxModel, UUID> {
    List<ExecutionCommandOutboxModel> findTop50ByPublishedAtIsNullAndAttemptCountLessThanOrderByCreatedAt(
            int maxAttempts);
}
