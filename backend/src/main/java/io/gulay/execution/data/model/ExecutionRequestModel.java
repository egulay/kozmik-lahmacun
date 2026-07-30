package io.gulay.execution.data.model;

import io.gulay.entity.data.model.BusinessEntityModel;
import io.gulay.user.data.model.AppUserReferenceModel;
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
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

@Entity
@Table(name = "execution_request")
@Getter
@Builder
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor(access = AccessLevel.PRIVATE)
public class ExecutionRequestModel {
    @Id
    private UUID id;
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "owner_user_id", nullable = false)
    private AppUserReferenceModel owner;
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "entity_id", nullable = false)
    private BusinessEntityModel entity;
    @Column(name = "execution_type", nullable = false)
    private String executionType;
    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private ExecutionStatus status;
    @Column(name = "original_request", nullable = false)
    private String originalRequest;
    @Column(name = "requested_language", nullable = false)
    private String requestedLanguage;
    @Column(name = "execution_order_version", nullable = false)
    private String executionOrderVersion;
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "execution_order_json", nullable = false, columnDefinition = "jsonb")
    private String executionOrderJson;
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "authorization_snapshot", nullable = false, columnDefinition = "jsonb")
    private String authorizationSnapshot;
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "configuration_snapshot", nullable = false, columnDefinition = "jsonb")
    private String configurationSnapshot;
    @Column(name = "idempotency_key", nullable = false)
    private String idempotencyKey;
    @Column(name = "request_fingerprint", nullable = false)
    private String requestFingerprint;
    @Column(name = "correlation_id", nullable = false)
    private String correlationId;
    @Column(name = "requested_at", nullable = false)
    private Instant requestedAt;
    @Column(name = "started_at")
    private Instant startedAt;
    @Column(name = "completed_at")
    private Instant completedAt;
    @Column(name = "cancel_requested_at")
    private Instant cancelRequestedAt;
    @Column(name = "timeout_at")
    private Instant timeoutAt;
    @Column(name = "retention_eligible_at")
    private Instant retentionEligibleAt;
    @Column(name = "deleted_at")
    private Instant deletedAt;

    public boolean completePlanning(String orderVersion, String orderJson) {
        if (status != ExecutionStatus.PLANNING
                || !"PENDING".equals(executionOrderVersion)
                || !"{}".equals(executionOrderJson)) {
            return false;
        }
        executionOrderVersion = orderVersion;
        executionOrderJson = orderJson;
        status = ExecutionStatus.VALIDATED;
        return true;
    }

    public boolean applyStatus(ExecutionStatus next, Instant occurredAt) {
        if (status.terminal()) {
            return status == next;
        }
        status = next;
        if (startedAt == null && (next == ExecutionStatus.RUNNING || next == ExecutionStatus.QUEUED)) {
            startedAt = occurredAt;
        }
        if (next.terminal()) {
            completedAt = occurredAt;
        }
        return true;
    }

    public boolean requestCancellation(Instant now) {
        if (status.terminal() || cancelRequestedAt != null) return false;
        cancelRequestedAt = now;
        return true;
    }
}
