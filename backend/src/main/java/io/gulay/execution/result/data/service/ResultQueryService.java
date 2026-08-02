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
            UUID executionId, String keycloakUserId, Set<PlatformRole> roles,
            int page, int size) {
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
            val preview = mapper.readTree(result.getPreviewJson());
            val rows = preview.path("rows");
            val totalElements = rows.isArray() ? rows.size() : 0;
            val totalPages = totalElements == 0 ? 0
                    : (int) Math.ceil((double) totalElements / size);
            val start = (int) Math.min((long) page * size, totalElements);
            val end = Math.min(start + size, totalElements);
            val pagedRows = mapper.createArrayNode();
            for (var index = start; index < end; index++) {
                pagedRows.add(rows.get(index));
            }
            val pagedPreview = mapper.createObjectNode();
            pagedPreview.set("columns", preview.path("columns"));
            pagedPreview.set("rows", pagedRows);
            pagedPreview.put("limit", size);
            pagedPreview.put("truncated", preview.path("truncated").asBoolean(false));
            return new ResultDtos.ResultResponse("1.0", executionId, result.getRowCount(),
                    pagedPreview, mapper.readTree(result.getKpisJson()),
                    mapper.readTree(result.getChartsJson()), mapper.readTree(result.getWarningsJson()),
                    new ResultDtos.ArtifactResponse(artifact.getId(), artifact.getFormat()),
                    "result.guidance.governedPreview",
                    result.getSummaryStatus(), result.getManagementSummary(),
                    result.getSummaryValidationStatus(),
                    page, size, totalElements, totalPages);
        } catch (Exception exception) {
            throw new IllegalStateException("Stored result is invalid", exception);
        }
    }

}
