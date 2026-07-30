package io.gulay.ingestion.data.model;

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
@Table(name = "ingestion_stream_batch")
@Getter
@Builder
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor(access = AccessLevel.PRIVATE)
public class IngestionStreamBatchModel {
    @Id
    @Column(name = "chunk_id")
    private UUID chunkId;
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "stream_id", nullable = false)
    private IngestionStreamModel stream;
    @Column(name = "sequence_number", nullable = false)
    private long sequenceNumber;
    @Column(name = "kafka_partition", nullable = false)
    private int kafkaPartition;
    @Column(name = "first_offset", nullable = false)
    private long firstOffset;
    @Column(name = "last_offset", nullable = false)
    private long lastOffset;
    @Column(name = "row_count")
    private Long rowCount;
    @Column(nullable = false)
    private String status;
    @Column(name = "refined_bucket")
    private String refinedBucket;
    @Column(name = "refined_object_key")
    private String refinedObjectKey;
    @Column(name = "produced_at", nullable = false)
    private Instant producedAt;
    @Column(name = "completed_at")
    private Instant completedAt;
    @Column(name = "error_code")
    private String errorCode;
    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    public void complete(long rows, String bucket, String key, Instant at) {
        rowCount = rows;
        refinedBucket = bucket;
        refinedObjectKey = key;
        completedAt = at;
        errorCode = null;
        status = "COMPLETED";
    }

    public void fail(String code, Instant at) {
        errorCode = code;
        completedAt = at;
        status = "FAILED";
    }
}
