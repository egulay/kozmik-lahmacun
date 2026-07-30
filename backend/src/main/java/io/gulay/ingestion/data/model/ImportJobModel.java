package io.gulay.ingestion.data.model;

import io.gulay.entity.data.model.BusinessEntityModel;
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
@Table(name = "import_job")
@Getter
@Builder
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor(access = AccessLevel.PRIVATE)
public class ImportJobModel {
    @Id
    private UUID id;
    @Column(name = "source_event_id", nullable = false, unique = true)
    private UUID sourceEventId;
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "entity_id", nullable = false)
    private BusinessEntityModel entity;
    @Column(name = "source_type", nullable = false)
    private String sourceType;
    @Column(name = "source_reference", nullable = false)
    private String sourceReference;
    @Column(nullable = false)
    private String status;
    @Column(name = "refined_bucket")
    private String refinedBucket;
    @Column(name = "refined_object_key")
    private String refinedObjectKey;
    @Column(name = "row_count")
    private Long rowCount;
    @Column(name = "created_at", nullable = false)
    private Instant createdAt;
    @Column(name = "started_at")
    private Instant startedAt;
    @Column(name = "completed_at")
    private Instant completedAt;
    @Column(name = "error_code")
    private String errorCode;
    @Column(name = "error_message")
    private String errorMessage;

    public void apply(String next, Instant at, Long rows,
                      String bucket, String key, String code, String message) {
        status = next;
        if (startedAt == null && ("RUNNING".equals(next) || "VALIDATING".equals(next))) startedAt = at;
        if ("COMPLETED".equals(next) || "FAILED".equals(next)) completedAt = at;
        if (rows != null) rowCount = rows;
        if (bucket != null) refinedBucket = bucket;
        if (key != null) refinedObjectKey = key;
        errorCode = code;
        errorMessage = message;
    }
}
