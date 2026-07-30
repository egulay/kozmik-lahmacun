package io.gulay.execution.result.data.service;

import lombok.val;

import tools.jackson.databind.ObjectMapper;
import io.gulay.api.ResourceNotFoundException;
import io.gulay.execution.data.repository.ExecutionRequestRepository;
import io.gulay.execution.dto.ResultDtos;
import io.gulay.execution.result.data.repository.ExecutionArtifactRepository;
import io.gulay.execution.result.data.repository.ExecutionResultRepository;

import java.util.UUID;
import java.util.Set;

import io.gulay.security.PlatformRole;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
public class ResultQueryService {
    private final ExecutionRequestRepository executions;
    private final ExecutionResultRepository results;
    private final ExecutionArtifactRepository artifacts;
    private final ObjectMapper mapper;

    @Transactional(readOnly = true)
    public ResultDtos.ResultResponse result(
            UUID executionId, String keycloakUserId, Set<PlatformRole> roles) {
        val execution = roles.contains(PlatformRole.ADMIN)
                ? executions.findById(executionId)
                : executions.findByIdAndOwnerKeycloakUserId(executionId, keycloakUserId);
        execution.filter(item -> item.getDeletedAt() == null)
                .orElseThrow(() -> new ResourceNotFoundException("Result not found"));
        val result = results.findByExecutionId(executionId)
                .orElseThrow(() -> new ResourceNotFoundException("Result not found"));
        val artifact = artifacts.findByResultId(result.getId()).stream().findFirst()
                .orElseThrow(() -> new IllegalStateException("Result artifact is missing"));
        try {
            return new ResultDtos.ResultResponse("1.0", executionId, result.getRowCount(),
                    mapper.readTree(result.getPreviewJson()), mapper.readTree(result.getKpisJson()),
                    mapper.readTree(result.getChartsJson()), mapper.readTree(result.getWarningsJson()),
                    new ResultDtos.ArtifactResponse(artifact.getId(), artifact.getFormat()),
                    "result.guidance.governedPreview",
                    result.getSummaryStatus(), result.getManagementSummary());
        } catch (Exception exception) {
            throw new IllegalStateException("Stored result is invalid", exception);
        }
    }

}
