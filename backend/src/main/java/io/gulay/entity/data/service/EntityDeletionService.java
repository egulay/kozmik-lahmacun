package io.gulay.entity.data.service;

import io.gulay.api.ConflictException;
import io.gulay.api.ResourceNotFoundException;
import io.gulay.audit.data.model.AuditOutcome;
import io.gulay.audit.data.service.AuditEventService;
import io.gulay.entity.client.EntityArtifactDeletionClient;
import io.gulay.entity.data.repository.BusinessEntityRepository;
import io.gulay.entity.data.repository.EntityDeletionRepository;
import io.gulay.execution.data.service.ExecutionDeletionService;
import io.gulay.security.PlatformRole;
import io.gulay.streaming.WorkspaceEventHub;
import io.gulay.user.data.repository.AppUserReferenceRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import lombok.val;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Set;
import java.util.UUID;

@Service
@RequiredArgsConstructor
@Slf4j
public class EntityDeletionService {
    private static final Duration RETRY = Duration.ofSeconds(10);
    private final BusinessEntityRepository entities;
    private final AppUserReferenceRepository users;
    private final EntityDeletionRepository repository;
    private final ExecutionDeletionService executionDeletion;
    private final EntityArtifactDeletionClient artifactDeletion;
    private final AuditEventService audit;
    private final WorkspaceEventHub workspaceEvents;
    private final Clock clock;

    public boolean delete(UUID entityId, String keycloakUserId, String correlationId) {
        if (!entities.existsById(entityId)) throw new ResourceNotFoundException("Entity not found");
        val actor = users.findByKeycloakUserId(keycloakUserId)
                .orElseThrow(() -> new ResourceNotFoundException("User reference not found"));
        if (repository.tombstoned(entityId)) throw new ConflictException("Entity deletion is already pending");
        val jobId = UUID.randomUUID();
        repository.prepare(jobId, entityId, actor.getId(), correlationId, Instant.now(clock));
        audit.record("ENTITY_DELETE_REQUESTED", actor, "ENTITY", entityId.toString(),
                correlationId, AuditOutcome.SUCCEEDED, "UUID_PERMANENTLY_RETIRED");
        log.warn("entity_delete_requested entityId={} jobId={} uuidRetired=true", entityId, jobId);
        workspaceEvents.publishAll("entity-deletion-changed", entityId.toString());
        process(new EntityDeletionRepository.DeletionJob(
                jobId, entityId, actor.getId(), keycloakUserId, correlationId));
        return !entities.existsById(entityId);
    }

    @Scheduled(fixedDelayString = "${kozmik.entity.deletion-retry-ms:10000}")
    public void retryPending() { repository.findReady(Instant.now(clock)).forEach(this::process); }

    private void process(EntityDeletionRepository.DeletionJob job) {
        val now = Instant.now(clock);
        if (!repository.claim(job.id(), now, now.plusSeconds(90))) return;
        try {
            if (repository.hasActiveWork(job.entityId())) {
                repository.waitUntil(job.id(), now.plus(RETRY));
                return;
            }
            for (val executionId : repository.terminalExecutions(job.entityId())) {
                if (!executionDeletion.delete(executionId, job.actorKeycloakId(),
                        Set.of(PlatformRole.ADMIN), job.correlationId())) {
                    repository.waitUntil(job.id(), now.plus(RETRY));
                    return;
                }
            }
            artifactDeletion.delete(job.entityId(), job.correlationId());
            repository.complete(job, Instant.now(clock));
            users.findById(job.actorId()).ifPresent(actor -> audit.record(
                    "ENTITY_DELETE_COMPLETED", actor, "ENTITY", job.entityId().toString(),
                    job.correlationId(), AuditOutcome.SUCCEEDED, "POSTGRES_AND_OBJECTS_DELETED"));
            workspaceEvents.publishAll("entity-deleted", job.entityId().toString());
            log.warn("entity_delete_completed entityId={} uuidReusable=false", job.entityId());
        } catch (RuntimeException exception) {
            repository.retry(job.id(), now.plus(RETRY), "ENTITY_DELETE_FAILED");
            log.error("entity_delete_retry_scheduled entityId={}", job.entityId(), exception);
        }
    }
}
