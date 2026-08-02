package io.gulay.execution.data.service;

import lombok.val;

import tools.jackson.databind.ObjectMapper;
import io.gulay.api.ResourceNotFoundException;
import io.gulay.execution.data.model.ExecutionDatasetBindingModel;
import io.gulay.execution.data.model.ExecutionStreamBindingModel;
import io.gulay.execution.data.repository.ExecutionDatasetBindingRepository;
import io.gulay.execution.data.repository.ExecutionRequestRepository;
import io.gulay.execution.data.repository.ExecutionStreamBindingRepository;
import io.gulay.execution.dto.GovernedDatasetDtos;
import io.gulay.ingestion.data.repository.ImportJobRepository;
import io.gulay.ingestion.data.repository.IngestionStreamRepository;

import java.util.UUID;
import java.time.Clock;
import java.time.Instant;

import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
public class GovernedDatasetResolutionService {
    private final ExecutionRequestRepository executions;
    private final ExecutionDatasetBindingRepository bindings;
    private final ImportJobRepository imports;
    private final ExecutionStreamBindingRepository streamBindings;
    private final IngestionStreamRepository streams;
    private final ObjectMapper mapper;
    private final Clock clock;

    @Transactional
    public GovernedDatasetDtos.GovernedDatasetResponse resolve(UUID executionId) {
        val execution = executions.findById(executionId)
                .orElseThrow(() -> new ResourceNotFoundException("Execution not found"));
        val entityId = execution.getEntity().getId();
        val fileBinding = bindings.findById(executionId);
        if (fileBinding.isPresent()) {
            return fileResponse(execution, fileBinding.get(), entityId);
        }
        val streamBinding = streamBindings.findById(executionId);
        if (streamBinding.isPresent()) {
            return streamResponse(execution, streamBinding.get(), entityId);
        }
        val imported = imports
                .findFirstByEntityIdAndStatusAndRefinedBucketIsNotNullAndRefinedObjectKeyIsNotNullOrderByCompletedAtDesc(
                        entityId, "COMPLETED");
        if (imported.isPresent()) {
            val binding = ExecutionDatasetBindingModel.builder()
                    .executionId(executionId).importJob(imported.get())
                    .resolvedAt(Instant.now(clock)).build();
            bindings.save(binding);
            return fileResponse(execution, binding, entityId);
        }
        // Streams are intentionally open-ended. While a new chunk is INGESTING,
        // earlier checkpointed parts remain immutable and safe for analytics.
        // Persisting the sequence/offset here gives this execution a stable snapshot.
        val stream = streams
                .findFirstByEntityIdAndLastSequenceIsNotNullAndLastOffsetIsNotNullOrderByUpdatedAtDesc(
                        entityId)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "No governed dataset is available for the execution schema"));
        val binding = ExecutionStreamBindingModel.builder()
                .executionId(executionId).stream(stream)
                .throughSequence(stream.getLastSequence())
                .throughOffset(stream.getLastOffset())
                .snapshotRowCount(stream.getCumulativeRows())
                .resolvedAt(Instant.now(clock)).build();
        streamBindings.save(binding);
        return streamResponse(execution, binding, entityId);
    }

    private GovernedDatasetDtos.GovernedDatasetResponse fileResponse(
            io.gulay.execution.data.model.ExecutionRequestModel execution,
            ExecutionDatasetBindingModel binding, UUID entityId) {
        val dataset = binding.getImportJob();
        if (!dataset.getEntity().getId().equals(entityId)
                || !"COMPLETED".equals(dataset.getStatus())) {
            throw new IllegalStateException("Persisted dataset binding is invalid");
        }
        val expectedPrefix = "entities/" + entityId + "/imports/" + dataset.getId() + "/";
        val parquetObject = dataset.getRefinedObjectKey().endsWith(".parquet");
        if (!"refined".equals(dataset.getRefinedBucket())
                || !dataset.getRefinedObjectKey().startsWith(expectedPrefix)
                || !parquetObject
                || dataset.getRowCount() == null
                || dataset.getRowCount() < 0) {
            throw new IllegalStateException("Governed dataset metadata is unsafe");
        }
        try {
            return new GovernedDatasetDtos.GovernedDatasetResponse(
                    "1.0", execution.getId(), entityId, dataset.getId(),
                    null, null, "PARQUET",
                    dataset.getRefinedBucket(), dataset.getRefinedObjectKey(),
                    dataset.getRowCount(), execution.getExecutionType(),
                    execution.getOwner().getId(),
                    mapper.readTree(execution.getExecutionOrderJson()),
                    mapper.readTree(execution.getAuthorizationSnapshot()),
                    mapper.readTree(execution.getConfigurationSnapshot()));
        } catch (Exception exception) {
            throw new IllegalStateException("Stored execution context is invalid", exception);
        }
    }

    private GovernedDatasetDtos.GovernedDatasetResponse streamResponse(
            io.gulay.execution.data.model.ExecutionRequestModel execution,
            ExecutionStreamBindingModel binding, UUID entityId) {
        val stream = binding.getStream();
        if (!stream.getEntity().getId().equals(entityId)
                || binding.getThroughSequence() < 0 || binding.getThroughOffset() < 0) {
            throw new IllegalStateException("Persisted stream binding is invalid");
        }
        val key = "entities/" + entityId + "/streams/" + stream.getId() + "/dataset";
        try {
            return new GovernedDatasetDtos.GovernedDatasetResponse(
                    "1.0", execution.getId(), entityId, null,
                    stream.getId(), binding.getThroughSequence(), "PARQUET_DATASET",
                    "refined", key, binding.getSnapshotRowCount(),
                    execution.getExecutionType(), execution.getOwner().getId(),
                    mapper.readTree(execution.getExecutionOrderJson()),
                    mapper.readTree(execution.getAuthorizationSnapshot()),
                    mapper.readTree(execution.getConfigurationSnapshot()));
        } catch (Exception exception) {
            throw new IllegalStateException("Stored execution context is invalid", exception);
        }
    }
}
