package io.gulay.execution;

import lombok.val;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import tools.jackson.databind.ObjectMapper;
import io.gulay.entity.data.model.BusinessEntityModel;
import io.gulay.execution.data.model.ExecutionRequestModel;
import io.gulay.execution.data.repository.ExecutionRequestRepository;
import io.gulay.execution.data.repository.ExecutionDatasetBindingRepository;
import io.gulay.execution.data.repository.ExecutionStreamBindingRepository;
import io.gulay.execution.data.service.GovernedDatasetResolutionService;
import io.gulay.ingestion.data.model.ImportJobModel;
import io.gulay.ingestion.data.repository.ImportJobRepository;
import io.gulay.ingestion.data.repository.IngestionStreamRepository;
import io.gulay.user.data.model.AppUserReferenceModel;
import java.util.Optional;
import java.util.UUID;
import java.time.Clock;
import org.junit.jupiter.api.Test;

class GovernedDatasetResolutionServiceTest {
    @Test
    void resolvesLatestCompletedArtifactForExactExecutionEntityAndSchema() {
        val executionId = UUID.randomUUID();
        val entityId = UUID.randomUUID();
        val importId = UUID.randomUUID();
        val entity = mock(BusinessEntityModel.class);
        val execution = mock(ExecutionRequestModel.class);
        val owner = mock(AppUserReferenceModel.class);
        val dataset = mock(ImportJobModel.class);
        val executions = mock(ExecutionRequestRepository.class);
        val bindings = mock(ExecutionDatasetBindingRepository.class);
        val imports = mock(ImportJobRepository.class);
        val streamBindings = mock(ExecutionStreamBindingRepository.class);
        val streams = mock(IngestionStreamRepository.class);
        when(entity.getId()).thenReturn(entityId);
        when(execution.getEntity()).thenReturn(entity);
        when(execution.getId()).thenReturn(executionId);
        when(execution.getOwner()).thenReturn(owner);
        when(owner.getId()).thenReturn(UUID.randomUUID());
        when(execution.getExecutionType()).thenReturn("REPORT");
        when(execution.getExecutionOrderJson()).thenReturn("{}");
        when(execution.getAuthorizationSnapshot()).thenReturn("{}");
        when(execution.getConfigurationSnapshot()).thenReturn("{}");
        when(executions.findById(executionId)).thenReturn(Optional.of(execution));
        when(dataset.getId()).thenReturn(importId);
        when(dataset.getEntity()).thenReturn(entity);
        when(dataset.getStatus()).thenReturn("COMPLETED");
        when(dataset.getRefinedBucket()).thenReturn("refined");
        when(dataset.getRefinedObjectKey()).thenReturn(
                "entities/" + entityId + "/imports/" + importId
                        + "/data.parquet");
        when(dataset.getRowCount()).thenReturn(125L);
        when(imports
                .findFirstByEntityIdAndStatusAndRefinedBucketIsNotNullAndRefinedObjectKeyIsNotNullOrderByCompletedAtDesc(
                        entityId, "COMPLETED"))
                .thenReturn(Optional.of(dataset));

        val response = new GovernedDatasetResolutionService(
                executions, bindings, imports, streamBindings, streams,
                new ObjectMapper(), Clock.systemUTC())
                .resolve(executionId);

        assertThat(response.executionId()).isEqualTo(executionId);
        assertThat(response.entityId()).isEqualTo(entityId);
        assertThat(response.importId()).isEqualTo(importId);
        assertThat(response.format()).isEqualTo("PARQUET");
        assertThat(response.bucket()).isEqualTo("refined");
        assertThat(response.rowCount()).isEqualTo(125);
        verify(imports)
                .findFirstByEntityIdAndStatusAndRefinedBucketIsNotNullAndRefinedObjectKeyIsNotNullOrderByCompletedAtDesc(
                        entityId, "COMPLETED");
    }
}
