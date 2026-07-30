package io.gulay.execution.data.service;

import lombok.val;

import tools.jackson.databind.ObjectMapper;
import io.gulay.api.ResourceNotFoundException;
import io.gulay.execution.data.repository.ExecutionRequestRepository;
import io.gulay.execution.data.repository.ExecutionStatusHistoryRepository;
import io.gulay.execution.dto.ExecutionDtos;
import io.gulay.execution.failure.data.repository.ExecutionFailureRepository;

import java.util.UUID;

import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

import java.util.Set;

import io.gulay.execution.data.model.ExecutionStatus;
import io.gulay.security.PlatformRole;

@Service
@RequiredArgsConstructor
public class ExecutionQueryService {
    private final ExecutionRequestRepository executions;
    private final ExecutionStatusHistoryRepository history;
    private final ExecutionFailureRepository failures;
    private final ObjectMapper objectMapper;

    @Transactional(readOnly = true)
    public ExecutionDtos.ExecutionStateResponse state(
            UUID id, String keycloakUserId, Set<PlatformRole> roles) {
        val execution = roles.contains(PlatformRole.ADMIN)
                ? executions.findById(id)
                : executions.findByIdAndOwnerKeycloakUserId(id, keycloakUserId);
        val authorized = execution
                .filter(item -> item.getDeletedAt() == null)
                .orElseThrow(() -> new ResourceNotFoundException("Execution not found"));
        try {
            val events = history.findByExecutionIdOrderByOccurredAtAsc(id).stream()
                    .map(item -> {
                        try {
                            return new ExecutionDtos.StatusHistoryResponse(
                                    item.getEventId(), item.getStage(), item.getStatus().name(),
                                    item.getProgress(), item.getMessageCode(),
                                    objectMapper.readTree(item.getMessageParameters()),
                                    item.getOccurredAt());
                        } catch (Exception exception) {
                            throw new IllegalStateException("Stored history is invalid", exception);
                        }
                    }).toList();
            val failure = failures.findByExecutionId(id)
                    .map(item -> new ExecutionDtos.ExecutionFailureResponse(
                            item.getSchemaVersion(), item.getFailureCode(),
                            item.getFailedStage(), item.getSanitizedTechnicalReason(),
                            item.getUserExplanation(), item.getExplanationStatus(),
                            item.isRetryable(), item.getLanguage(), item.getCreatedAt()))
                    .orElse(null);
            return new ExecutionDtos.ExecutionStateResponse(
                    "1.0", authorized.getId(), authorized.getExecutionType(),
                    authorized.getStatus().name(), authorized.getEntity().getId(),
                    authorized.getEntity().getName(), authorized.getOwner().getDisplayName(),
                    authorized.getOriginalRequest(), authorized.getRequestedAt(),
                    authorized.getStartedAt(), authorized.getCompletedAt(),
                    objectMapper.readTree(authorized.getExecutionOrderJson()), events,
                    failure);
        } catch (Exception exception) {
            throw new IllegalStateException("Stored execution state is invalid", exception);
        }
    }

    @Transactional(readOnly = true)
    public ExecutionDtos.ExecutionListResponse list(
            String keycloakUserId, int page, int size,
            Set<ExecutionStatus> statuses, String search, Set<PlatformRole> roles) {
        val requestedStatuses = statuses == null || statuses.isEmpty()
                ? Set.of(ExecutionStatus.values()) : statuses;
        val pageable = PageRequest.of(page, size, Sort.by(
                Sort.Order.desc("requestedAt"), Sort.Order.desc("id")));
        val normalizedSearch = search == null ? "" : search.trim();
        val resultPage = roles.contains(PlatformRole.ADMIN)
                ? executions.findAdminPage(requestedStatuses, normalizedSearch, pageable)
                : executions.findVisiblePage(
                keycloakUserId, requestedStatuses, normalizedSearch, pageable);
        val items = resultPage
                .stream()
                .map(execution -> new ExecutionDtos.ExecutionSummaryResponse(
                        execution.getId(),
                        execution.getExecutionType(),
                        execution.getStatus().name(),
                        execution.getEntity().getId(),
                        execution.getEntity().getName(),
                        execution.getOwner().getDisplayName(),
                        execution.getOriginalRequest(),
                        execution.getRequestedAt(),
                        execution.getStartedAt(),
                        execution.getCompletedAt()))
                .toList();
        return new ExecutionDtos.ExecutionListResponse(
                "1.0", items, resultPage.getNumber(), resultPage.getSize(),
                resultPage.getTotalElements(), resultPage.getTotalPages(),
                resultPage.isFirst(), resultPage.isLast());
    }
}
