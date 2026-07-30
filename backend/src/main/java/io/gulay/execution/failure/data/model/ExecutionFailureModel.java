package io.gulay.execution.failure.data.model;

import io.gulay.execution.data.model.ExecutionRequestModel;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.OneToOne;
import jakarta.persistence.Table;

import java.time.Instant;
import java.util.UUID;

import lombok.AccessLevel;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Entity
@Table(name = "execution_failure")
@Getter
@Builder
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor(access = AccessLevel.PRIVATE)
public class ExecutionFailureModel {
    @Id
    private UUID id;
    @OneToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "execution_id", nullable = false, unique = true)
    private ExecutionRequestModel execution;
    @Column(name = "schema_version", nullable = false)
    private String schemaVersion;
    @Column(name = "failure_code", nullable = false)
    private String failureCode;
    @Column(name = "failed_stage", nullable = false)
    private String failedStage;
    @Column(name = "sanitized_technical_reason", nullable = false, length = 1000)
    private String sanitizedTechnicalReason;
    @Column(name = "user_explanation", nullable = false, length = 2000)
    private String userExplanation;
    @Column(name = "explanation_status", nullable = false)
    private String explanationStatus;
    @Column(nullable = false)
    private boolean retryable;
    @Column(nullable = false, length = 2)
    private String language;
    @Column(name = "created_at", nullable = false)
    private Instant createdAt;
}
