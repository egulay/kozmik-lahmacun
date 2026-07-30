package io.gulay.user.data.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

import java.time.Instant;
import java.util.UUID;

import lombok.AccessLevel;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Entity
@Table(name = "user_management_operation")
@Getter
@Builder
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor(access = AccessLevel.PRIVATE)
public class UserManagementOperationModel {
    @Id
    private UUID id;

    @ManyToOne(fetch = FetchType.EAGER)
    @JoinColumn(name = "target_user_id", nullable = false)
    private AppUserReferenceModel target;

    @ManyToOne(fetch = FetchType.EAGER)
    @JoinColumn(name = "actor_user_id", nullable = false)
    private AppUserReferenceModel actor;

    @Enumerated(EnumType.STRING)
    @Column(name = "operation_type", nullable = false)
    private UserOperationType operationType;

    @Column(name = "desired_display_name")
    private String desiredDisplayName;
    @Column(name = "desired_email")
    private String desiredEmail;
    @Column(name = "desired_roles")
    private String desiredRoles;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private UserOperationStatus status;

    @Column(name = "attempt_count", nullable = false)
    private int attemptCount;
    @Column(name = "next_attempt_at", nullable = false)
    private Instant nextAttemptAt;
    @Column(name = "correlation_id", nullable = false)
    private String correlationId;
    @Column(name = "last_error_code")
    private String lastErrorCode;
    @Column(name = "requested_at", nullable = false)
    private Instant requestedAt;
    @Column(name = "completed_at")
    private Instant completedAt;

    public void processing(Instant leaseUntil) {
        status = UserOperationStatus.PROCESSING;
        attemptCount++;
        nextAttemptAt = leaseUntil;
    }

    public void retry(Instant next, String errorCode) {
        status = UserOperationStatus.RETRY_PENDING;
        nextAttemptAt = next;
        lastErrorCode = errorCode;
    }

    public void complete(Instant now) {
        status = UserOperationStatus.COMPLETED;
        completedAt = now;
        lastErrorCode = null;
    }
}
