package io.gulay.execution.controller;

import io.gulay.execution.data.service.GovernedDatasetResolutionService;
import io.gulay.execution.dto.GovernedDatasetDtos;

import java.util.UUID;

import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/internal/v1/executions")
@RequiredArgsConstructor
public class InternalExecutionController {
    private final GovernedDatasetResolutionService datasets;

    @GetMapping("/{executionId}/dataset")
    GovernedDatasetDtos.GovernedDatasetResponse dataset(@PathVariable UUID executionId) {
        return datasets.resolve(executionId);
    }
}
