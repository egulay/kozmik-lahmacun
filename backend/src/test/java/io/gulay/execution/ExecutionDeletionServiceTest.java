package io.gulay.execution;

import lombok.val;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.mockito.Mockito.doThrow;

import io.gulay.api.ConflictException;
import io.gulay.api.ResourceNotFoundException;
import io.gulay.audit.data.service.AuditEventService;
import io.gulay.execution.client.ExecutionArtifactDeletionClient;
import io.gulay.execution.client.ExecutionArtifactDeletionClient.ArtifactLocation;
import io.gulay.execution.data.model.ExecutionRequestModel;
import io.gulay.execution.data.model.ExecutionStatus;
import io.gulay.execution.data.repository.ExecutionDeletionRepository;
import io.gulay.execution.data.repository.ExecutionRequestRepository;
import io.gulay.execution.data.service.ExecutionDeletionService;
import io.gulay.security.PlatformRole;
import io.gulay.user.data.model.AppUserReferenceModel;
import io.gulay.user.data.repository.AppUserReferenceRepository;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.time.Clock;
import org.junit.jupiter.api.Test;

class ExecutionDeletionServiceTest {

    @Test
    void ownerDeletesTerminalExecutionArtifactsBeforeDatabaseGraph() {
        val fixture = fixture();
        when(fixture.executions.findByIdAndOwnerKeycloakUserId(
                fixture.executionId, fixture.keycloakId))
                .thenReturn(Optional.of(fixture.execution));

        fixture.service.delete(
                fixture.executionId, fixture.keycloakId,
                Set.of(PlatformRole.REPORTER), "correlation-1");

        verify(fixture.artifacts).delete(
                fixture.executionId, "correlation-1", fixture.locations);
        verify(fixture.deletions).complete(
                org.mockito.ArgumentMatchers.any(), org.mockito.ArgumentMatchers.any());
    }

    @Test
    void adminMayDeleteAnotherUsersTerminalExecution() {
        val fixture = fixture();
        when(fixture.executions.findById(fixture.executionId))
                .thenReturn(Optional.of(fixture.execution));

        fixture.service.delete(
                fixture.executionId, fixture.keycloakId,
                Set.of(PlatformRole.ADMIN), "correlation-2");

        verify(fixture.artifacts).delete(
                fixture.executionId, "correlation-2", fixture.locations);
        verify(fixture.deletions).complete(
                org.mockito.ArgumentMatchers.any(), org.mockito.ArgumentMatchers.any());
    }

    @Test
    void nonOwnerCannotDeleteExecution() {
        val fixture = fixture();
        when(fixture.executions.findByIdAndOwnerKeycloakUserId(
                fixture.executionId, fixture.keycloakId))
                .thenReturn(Optional.empty());

        assertThatThrownBy(() -> fixture.service.delete(
                fixture.executionId, fixture.keycloakId,
                Set.of(PlatformRole.REPORTER), "correlation-3"))
                .isInstanceOf(ResourceNotFoundException.class);

        verify(fixture.artifacts, never()).delete(
                fixture.executionId, "correlation-3", fixture.locations);
        verify(fixture.deletions, never()).complete(
                org.mockito.ArgumentMatchers.any(), org.mockito.ArgumentMatchers.any());
    }

    @Test
    void activeExecutionMustBeCancelledBeforeDeletion() {
        val fixture = fixture(ExecutionStatus.RUNNING);
        when(fixture.executions.findByIdAndOwnerKeycloakUserId(
                fixture.executionId, fixture.keycloakId))
                .thenReturn(Optional.of(fixture.execution));

        assertThatThrownBy(() -> fixture.service.delete(
                fixture.executionId, fixture.keycloakId,
                Set.of(PlatformRole.REPORTER), "correlation-4"))
                .isInstanceOf(ConflictException.class);

        verify(fixture.artifacts, never()).delete(
                fixture.executionId, "correlation-4", fixture.locations);
        verify(fixture.deletions, never()).complete(
                org.mockito.ArgumentMatchers.any(), org.mockito.ArgumentMatchers.any());
    }

    @Test
    void storageFailureLeavesDurableJobForAutomaticRetry() {
        val fixture = fixture();
        when(fixture.executions.findByIdAndOwnerKeycloakUserId(
                fixture.executionId, fixture.keycloakId))
                .thenReturn(Optional.of(fixture.execution));
        doThrow(new IllegalStateException("storage unavailable"))
                .when(fixture.artifacts)
                .delete(fixture.executionId, "correlation-5", fixture.locations);

        val completed = fixture.service.delete(
                fixture.executionId, fixture.keycloakId,
                Set.of(PlatformRole.REPORTER), "correlation-5");

        org.assertj.core.api.Assertions.assertThat(completed).isFalse();
        verify(fixture.deletions).retryLater(
                org.mockito.ArgumentMatchers.any(),
                org.mockito.ArgumentMatchers.any());
        verify(fixture.deletions, never()).complete(
                org.mockito.ArgumentMatchers.any(), org.mockito.ArgumentMatchers.any());
    }

    private Fixture fixture() {
        return fixture(ExecutionStatus.SUCCEEDED);
    }

    private Fixture fixture(ExecutionStatus status) {
        val executionId = UUID.randomUUID();
        val keycloakId = "owner-keycloak-id";
        val execution = mock(ExecutionRequestModel.class);
        val actor = mock(AppUserReferenceModel.class);
        val executions = mock(ExecutionRequestRepository.class);
        val users = mock(AppUserReferenceRepository.class);
        val artifacts = mock(ExecutionArtifactDeletionClient.class);
        val audit = mock(AuditEventService.class);
        val deletions = mock(ExecutionDeletionRepository.class);
        val locations = List.of(new ArtifactLocation(
                UUID.randomUUID(), "results",
                "executions/" + executionId + "/result.parquet"));
        when(users.findByKeycloakUserId(keycloakId)).thenReturn(Optional.of(actor));
        when(execution.getStatus()).thenReturn(status);
        when(execution.getDeletedAt()).thenReturn(null);
        when(deletions.findExecutionArtifacts(executionId)).thenReturn(locations);
        when(deletions.findJobArtifacts(org.mockito.ArgumentMatchers.any()))
                .thenReturn(locations);
        when(deletions.claim(
                org.mockito.ArgumentMatchers.any(),
                org.mockito.ArgumentMatchers.any(),
                org.mockito.ArgumentMatchers.any())).thenReturn(true);
        return new Fixture(
                executionId, keycloakId, execution, executions, artifacts,
                deletions, locations,
                new ExecutionDeletionService(
                        executions, users, artifacts, audit, deletions,
                        Clock.systemUTC()));
    }

    private record Fixture(
            UUID executionId,
            String keycloakId,
            ExecutionRequestModel execution,
            ExecutionRequestRepository executions,
            ExecutionArtifactDeletionClient artifacts,
            ExecutionDeletionRepository deletions,
            List<ArtifactLocation> locations,
            ExecutionDeletionService service) {
    }
}
