package io.gulay.execution.data.service;

import lombok.val;

import io.gulay.api.ConflictException;
import io.gulay.api.ResourceNotFoundException;
import io.gulay.audit.data.model.AuditOutcome;
import io.gulay.audit.data.service.AuditEventService;
import io.gulay.execution.client.ExecutionArtifactDeletionClient;
import io.gulay.execution.data.repository.ExecutionDeletionRepository;
import io.gulay.execution.data.repository.ExecutionDeletionRepository.DeletionJob;
import io.gulay.execution.data.repository.ExecutionRequestRepository;
import io.gulay.security.PlatformRole;
import io.gulay.user.data.repository.AppUserReferenceRepository;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Set;
import java.util.UUID;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
@Slf4j
public class ExecutionDeletionService {

    private static final Duration PROCESSING_LEASE = Duration.ofMinutes(2);
    private static final Duration RETRY_DELAY = Duration.ofSeconds(30);

    private final ExecutionRequestRepository executions;
    private final AppUserReferenceRepository users;
    private final ExecutionArtifactDeletionClient artifactDeletionClient;
    private final AuditEventService audit;
    private final ExecutionDeletionRepository deletionRepository;
    private final Clock clock;

    public boolean delete(
            UUID executionId,
            String keycloakUserId,
            Set<PlatformRole> roles,
            String correlationId) {
        val actor = users.findByKeycloakUserId(keycloakUserId)
                .orElseThrow(() -> new ResourceNotFoundException("User reference not found"));
        val candidate = roles.contains(PlatformRole.ADMIN)
                ? executions.findById(executionId)
                : executions.findByIdAndOwnerKeycloakUserId(executionId, keycloakUserId);
        val execution = candidate
                .filter(item -> item.getDeletedAt() == null)
                .orElseThrow(() -> new ResourceNotFoundException("Execution not found"));
        if (!execution.getStatus().terminal()) {
            throw new ConflictException(
                    "Only completed, failed, cancelled, or timed-out executions can be deleted");
        }

        val artifacts = deletionRepository.findExecutionArtifacts(executionId);
        val jobId = UUID.randomUUID();
        val now = Instant.now(clock);
        val actorRole = roles.contains(PlatformRole.ADMIN) ? "ADMIN" : "OWNER";
        deletionRepository.prepare(
                jobId, executionId, actor.getId(), correlationId, actorRole, now, artifacts);
        audit.record("EXECUTION_DELETE_REQUESTED", actor, "EXECUTION", executionId.toString(),
                correlationId, AuditOutcome.SUCCEEDED, actorRole + "_DELETE_PREPARED");
        log.info(
                "execution_delete_requested executionId={} deletionJobId={} artifactCount={} "
                        + "actorRole={}",
                executionId, jobId, artifacts.size(), actorRole);

        return process(new DeletionJob(
                jobId, executionId, actor.getId(), correlationId, actorRole));
    }

    @Scheduled(fixedDelayString = "${kozmik.execution.deletion-retry-ms:10000}")
    public void retryPending() {
        val jobs = deletionRepository.findReady(Instant.now(clock));
        if (!jobs.isEmpty()) {
            log.info("execution_delete_retry_scan pendingCount={}", jobs.size());
        }
        jobs.forEach(this::process);
    }

    private boolean process(DeletionJob job) {
        val now = Instant.now(clock);
        if (!deletionRepository.claim(job.id(), now, now.plus(PROCESSING_LEASE))) {
            return false;
        }
        val artifacts = deletionRepository.findJobArtifacts(job.id());
        try {
            artifactDeletionClient.delete(
                    job.executionId(), job.correlationId(), artifacts);
            deletionRepository.complete(job, Instant.now(clock));
        } catch (RuntimeException exception) {
            deletionRepository.retryLater(
                    job.id(), Instant.now(clock).plus(RETRY_DELAY));
            users.findById(job.actorId()).ifPresent(actor ->
                    audit.record("EXECUTION_DELETE_RETRY_SCHEDULED", actor, "EXECUTION",
                            job.executionId().toString(), job.correlationId(),
                            AuditOutcome.FAILED, "ARTIFACT_DELETE_FAILED"));
            log.error(
                    "execution_delete_retry_scheduled executionId={} deletionJobId={} "
                            + "code=ARTIFACT_DELETE_FAILED",
                    job.executionId(), job.id(), exception);
            return false;
        }
        try {
            users.findById(job.actorId()).ifPresent(actor ->
                    audit.record("EXECUTION_DELETE_COMPLETED", actor, "EXECUTION",
                            job.executionId().toString(), job.correlationId(),
                            AuditOutcome.SUCCEEDED, job.actorRole() + "_PHYSICAL_DELETE"));
        } catch (RuntimeException auditException) {
            log.error(
                    "execution_delete_audit_failed executionId={} deletionJobId={} "
                            + "code=AUDIT_WRITE_FAILED",
                    job.executionId(), job.id(), auditException);
        }
        log.info(
                "execution_delete_completed executionId={} deletionJobId={} "
                        + "artifactCount={} postgresDeleted=true minioDeleted=true",
                job.executionId(), job.id(), artifacts.size());
        return true;
    }
}
