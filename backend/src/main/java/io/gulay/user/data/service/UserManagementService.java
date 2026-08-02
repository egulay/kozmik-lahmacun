package io.gulay.user.data.service;

import lombok.val;

import io.gulay.api.ConflictException;
import io.gulay.api.ResourceNotFoundException;
import io.gulay.audit.data.model.AuditOutcome;
import io.gulay.audit.data.service.AuditEventService;
import io.gulay.user.client.KeycloakAdminClient;
import io.gulay.user.data.model.AppUserReferenceModel;
import io.gulay.user.data.model.UserManagementOperationModel;
import io.gulay.user.data.model.UserOperationStatus;
import io.gulay.user.data.model.UserOperationType;
import io.gulay.user.data.model.UserRole;
import io.gulay.user.data.model.UserStatus;
import io.gulay.user.data.repository.AppUserReferenceRepository;
import io.gulay.user.data.repository.UserManagementOperationRepository;
import io.gulay.user.dto.UserManagementDtos;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.UUID;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
@RequiredArgsConstructor
@Slf4j
public class UserManagementService {
    private static final Duration RETRY_DELAY = Duration.ofSeconds(30);
    private static final Duration PROCESSING_LEASE = Duration.ofMinutes(2);
    private final AppUserReferenceRepository users;
    private final UserManagementOperationRepository operations;
    private final AppUserReferenceService userReferences;
    private final KeycloakAdminClient keycloak;
    private final AuditEventService audit;
    private final TransactionTemplate transactions;
    private final FindByIndexNameSessionRepository<? extends Session> sessions;
    private final Clock clock;

    public UserManagementDtos.UserPage list(
            int page, int size, Set<UserStatus> statuses, String search) {
        reconcile();
        val requestedStatuses = statuses == null || statuses.isEmpty()
                ? Set.of(UserStatus.ACTIVE, UserStatus.SUSPENDED)
                : statuses.stream().filter(status -> status != UserStatus.DELETED)
                .collect(java.util.stream.Collectors.toUnmodifiableSet());
        val effectiveStatuses = requestedStatuses.isEmpty()
                ? Set.of(UserStatus.ACTIVE, UserStatus.SUSPENDED) : requestedStatuses;
        val normalizedSearch = search == null ? "" : search.trim();
        val result = users.findFilteredPage(effectiveStatuses, normalizedSearch,
                PageRequest.of(page, Math.min(Math.max(size, 1), 100),
                        Sort.by(Sort.Direction.ASC, "displayName")));
        return new UserManagementDtos.UserPage(
                result.getContent().stream().map(this::summary).toList(),
                result.getNumber(), result.getSize(), result.getTotalElements(),
                result.getTotalPages(), result.isFirst(), result.isLast());
    }

    public UserManagementDtos.OperationResponse update(
            UUID userId, UserManagementDtos.UpdateUserRequest request, String actorKeycloakId) {
        return submit(userId, actorKeycloakId, UserOperationType.UPDATE,
                request.displayName(),
                request.email().trim().toLowerCase(java.util.Locale.ROOT),
                request.roles());
    }

    public UserManagementDtos.UserSummary create(
            UserManagementDtos.CreateUserRequest request, String actorKeycloakId) {
        val actor = users.findByKeycloakUserId(actorKeycloakId)
                .orElseThrow(() -> new ResourceNotFoundException("Administrator not found"));
        KeycloakAdminClient.IdentityUser identity = null;
        val correlation = UUID.randomUUID().toString();
        val username = request.email().trim().toLowerCase(java.util.Locale.ROOT);
        try {
            identity = keycloak.create(
                    username, request.displayName(), username,
                    request.roles());
            keycloak.sendPasswordActionEmail(identity.id());
            val createdIdentity = identity;
            val created = transactions.execute(status -> {
                val local = userReferences.synchronizeIdentity(
                        createdIdentity.id(), createdIdentity.username(),
                        createdIdentity.displayName(), createdIdentity.email(),
                        createdIdentity.roles(), true);
                audit.record("USER_CREATED", actor, "USER", local.getId().toString(),
                        correlation, AuditOutcome.SUCCEEDED, "CREATE");
                return local;
            });
            log.info("user_created userId={} username={} actorId={} correlationId={}",
                    created.getId(), created.getUsername(), actor.getId(), correlation);
            return summary(created);
        } catch (RuntimeException exception) {
            if (identity != null) {
                try {
                    keycloak.delete(identity.id());
                } catch (RuntimeException compensationFailure) {
                    exception.addSuppressed(compensationFailure);
                    log.error("user_create_compensation_failed keycloakUserId={} correlationId={}",
                            identity.id(), correlation, compensationFailure);
                }
            }
            log.error("user_create_failed username={} actorId={} correlationId={}",
                    username, actor.getId(), correlation, exception);
            throw exception;
        }
    }

    public UserManagementDtos.OperationResponse suspend(UUID userId, String actorKeycloakId) {
        return submit(userId, actorKeycloakId, UserOperationType.SUSPEND, null, null, null);
    }

    public UserManagementDtos.PasswordActionResponse resetPassword(
            UUID userId, String actorKeycloakId) {
        val actor = users.findByKeycloakUserId(actorKeycloakId)
                .orElseThrow(() -> new ResourceNotFoundException("Administrator not found"));
        val target = users.findById(userId)
                .filter(user -> user.getStatus() != UserStatus.DELETED)
                .orElseThrow(() -> new ResourceNotFoundException("User not found"));
        keycloak.sendPasswordActionEmail(target.getKeycloakUserId());
        val correlation = UUID.randomUUID().toString();
        audit.record("USER_PASSWORD_RESET_EMAIL_SENT", actor, "USER", userId.toString(),
                correlation, AuditOutcome.SUCCEEDED, "UPDATE_PASSWORD");
        log.info("user_password_reset_email_sent userId={} actorId={} correlationId={}",
                userId, actor.getId(), correlation);
        return new UserManagementDtos.PasswordActionResponse("EMAIL_SENT");
    }

    public UserManagementDtos.PasswordActionResponse requestOwnPasswordChange(
            String actorKeycloakId) {
        val actor = users.findByKeycloakUserId(actorKeycloakId)
                .filter(user -> user.getStatus() == UserStatus.ACTIVE)
                .orElseThrow(() -> new ResourceNotFoundException("User not found"));
        keycloak.sendPasswordActionEmail(actorKeycloakId);
        val correlation = UUID.randomUUID().toString();
        audit.record("USER_PASSWORD_CHANGE_EMAIL_SENT", actor, "USER",
                actor.getId().toString(), correlation, AuditOutcome.SUCCEEDED,
                "UPDATE_PASSWORD");
        log.info("user_password_change_email_sent userId={} correlationId={}",
                actor.getId(), correlation);
        return new UserManagementDtos.PasswordActionResponse("EMAIL_SENT");
    }

    public UserManagementDtos.OperationResponse resume(UUID userId, String actorKeycloakId) {
        return submit(userId, actorKeycloakId, UserOperationType.RESUME, null, null, null);
    }

    public UserManagementDtos.OperationResponse delete(UUID userId, String actorKeycloakId) {
        return submit(userId, actorKeycloakId, UserOperationType.DELETE, null, null, null);
    }

    private UserManagementDtos.OperationResponse submit(
            UUID userId, String actorKeycloakId, UserOperationType type,
            String displayName, String email, Set<UserRole> roles) {
        val operation = transactions.execute(status -> {
            val target = users.findById(userId)
                    .filter(user -> user.getStatus() != UserStatus.DELETED)
                    .orElseThrow(() -> new ResourceNotFoundException("User not found"));
            val actor = users.findByKeycloakUserId(actorKeycloakId)
                    .orElseThrow(() -> new ResourceNotFoundException("Administrator not found"));
            if (target.getKeycloakUserId().equals(actorKeycloakId)
                    && type != UserOperationType.UPDATE) {
                throw new ConflictException("Administrators cannot suspend or delete themselves");
            }
            if (target.getKeycloakUserId().equals(actorKeycloakId)
                    && roles != null && !roles.contains(UserRole.ADMIN)) {
                throw new ConflictException("Administrators cannot remove their own ADMIN role");
            }
            val now = Instant.now(clock);
            val correlation = UUID.randomUUID().toString();
            val created = operations.save(UserManagementOperationModel.builder()
                    .id(UUID.randomUUID()).target(target).actor(actor).operationType(type)
                    .desiredDisplayName(displayName).desiredEmail(email)
                    .desiredRoles(roles == null ? null : encodeRoles(roles))
                    .status(UserOperationStatus.PENDING).attemptCount(0)
                    .nextAttemptAt(now).correlationId(correlation).requestedAt(now).build());
            audit.record("USER_MANAGEMENT_REQUESTED", actor, "USER", userId.toString(),
                    correlation, AuditOutcome.SUCCEEDED, type.name() + "_PREPARED");
            return created;
        });
        process(operation.getId());
        val current = operations.findById(operation.getId()).orElseThrow();
        return new UserManagementDtos.OperationResponse(
                current.getId(), userId, current.getStatus(), current.getCorrelationId());
    }

    @Scheduled(fixedDelayString = "${kozmik.keycloak.user-operation-retry-ms:10000}")
    public void retryPending() {
        operations.findByStatusInAndNextAttemptAtLessThanEqualOrderByRequestedAt(
                Set.of(UserOperationStatus.PENDING, UserOperationStatus.PROCESSING,
                        UserOperationStatus.RETRY_PENDING),
                Instant.now(clock), PageRequest.of(0, 20)).forEach(operation -> process(operation.getId()));
    }

    void process(UUID operationId) {
        val operation = transactions.execute(status -> {
            val item = operations.findById(operationId).orElseThrow();
            if (item.getStatus() == UserOperationStatus.COMPLETED) return null;
            item.processing(Instant.now(clock).plus(PROCESSING_LEASE));
            return operations.save(item);
        });
        if (operation == null) return;
        try {
            applyIdentity(operation);
            revokeBrowserSessions(operation);
            transactions.executeWithoutResult(status -> finalizeLocal(operation.getId()));
            log.info("user_management_completed operationId={} userId={} type={} correlationId={}",
                    operation.getId(), operation.getTarget().getId(),
                    operation.getOperationType(), operation.getCorrelationId());
        } catch (RuntimeException exception) {
            transactions.executeWithoutResult(status -> {
                val failed = operations.findById(operationId).orElseThrow();
                failed.retry(Instant.now(clock).plus(RETRY_DELAY), "KEYCLOAK_OPERATION_FAILED");
            });
            log.error("user_management_retry_scheduled operationId={} type={} code={}",
                    operationId, operation.getOperationType(), "KEYCLOAK_OPERATION_FAILED", exception);
        }
    }

    private void applyIdentity(UserManagementOperationModel operation) {
        val id = operation.getTarget().getKeycloakUserId();
        switch (operation.getOperationType()) {
            case UPDATE -> keycloak.update(id, operation.getDesiredDisplayName(),
                    operation.getDesiredEmail(), decodeRoles(operation.getDesiredRoles()));
            case SUSPEND -> keycloak.enabled(id, false);
            case RESUME -> keycloak.enabled(id, true);
            case DELETE -> keycloak.delete(id);
        }
    }

    private void revokeBrowserSessions(UserManagementOperationModel operation) {
        if (operation.getOperationType() == UserOperationType.RESUME) return;
        sessions.findByPrincipalName(operation.getTarget().getKeycloakUserId())
                .values().forEach(session -> sessions.deleteById(session.getId()));
    }

    private void finalizeLocal(UUID operationId) {
        val operation = operations.findById(operationId).orElseThrow();
        val target = operation.getTarget();
        val now = Instant.now(clock);
        val newStatus = switch (operation.getOperationType()) {
            case SUSPEND -> UserStatus.SUSPENDED;
            case RESUME, UPDATE -> UserStatus.ACTIVE;
            case DELETE -> UserStatus.DELETED;
        };
        val displayName = operation.getOperationType() == UserOperationType.UPDATE
                ? operation.getDesiredDisplayName() : target.getDisplayName();
        val email = operation.getOperationType() == UserOperationType.UPDATE
                ? operation.getDesiredEmail() : target.getEmail();
        val username = operation.getOperationType() == UserOperationType.UPDATE
                ? email.trim().toLowerCase(java.util.Locale.ROOT) : target.getUsername();
        val roles = operation.getOperationType() == UserOperationType.UPDATE
                ? decodeRoles(operation.getDesiredRoles()) : new LinkedHashSet<>(target.getRoles());
        target.applyManagementState(username, displayName, email, roles, newStatus, now);
        users.save(target);
        operation.complete(now);
        audit.record("USER_MANAGEMENT_COMPLETED", operation.getActor(), "USER",
                target.getId().toString(), operation.getCorrelationId(),
                AuditOutcome.SUCCEEDED, operation.getOperationType().name());
    }

    private void reconcile() {
        try {
            keycloak.users().forEach(identity -> userReferences.synchronizeIdentity(
                    identity.id(), identity.username(), identity.displayName(), identity.email(),
                    identity.roles(), identity.enabled()));
        } catch (RuntimeException exception) {
            log.warn("keycloak_user_reconciliation_failed code=KEYCLOAK_LIST_FAILED", exception);
        }
    }

    private UserManagementDtos.UserSummary summary(AppUserReferenceModel user) {
        return new UserManagementDtos.UserSummary(
                user.getId(), user.getKeycloakUserId(), user.getUsername(),
                user.getDisplayName(), user.getEmail(), user.getStatus(),
                Set.copyOf(user.getRoles()), user.getUpdatedAt());
    }

    private String encodeRoles(Set<UserRole> roles) {
        return roles.stream().map(Enum::name).sorted().collect(java.util.stream.Collectors.joining(","));
    }

    private Set<UserRole> decodeRoles(String roles) {
        if (roles == null || roles.isBlank()) return Set.of();
        return Arrays.stream(roles.split(",")).map(UserRole::valueOf)
                .collect(java.util.stream.Collectors.toCollection(LinkedHashSet::new));
    }
}
