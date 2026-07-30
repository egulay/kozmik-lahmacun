package io.gulay.execution.result.data.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
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
@Table(name = "execution_artifact")
@Getter
@Builder
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor(access = AccessLevel.PRIVATE)
public class ExecutionArtifactModel {
    @Id
    private UUID id;
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "execution_result_id", nullable = false)
    private ExecutionResultModel result;
    @Column(nullable = false)
    private String format;
    @Column(name = "bucket_name", nullable = false)
    private String bucketName;
    @Column(name = "object_key", nullable = false)
    private String objectKey;
    @Column(name = "size_bytes")
    private Long sizeBytes;
    @Column(name = "created_at", nullable = false)
    private Instant createdAt;
}
