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
@Table(name = "ingestion_stream")
@Getter
@Builder
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor(access = AccessLevel.PRIVATE)
public class IngestionStreamModel {
    @Id
    private UUID id;
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "entity_id", nullable = false)
    private BusinessEntityModel entity;
    @Column(name = "source_id", nullable = false)
    private String sourceId;
    @Column(nullable = false)
    private String topic;
    @Column(nullable = false)
    private String status;
    @Column(name = "cumulative_rows", nullable = false)
    private long cumulativeRows;
    @Column(name = "last_sequence")
    private Long lastSequence;
    @Column(name = "last_partition")
    private Integer lastPartition;
    @Column(name = "last_offset")
    private Long lastOffset;
    @Column(name = "last_error_code")
    private String lastErrorCode;
    @Column(name = "started_at", nullable = false)
    private Instant startedAt;
    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    public void checkpoint(
            long rows, long sequence, int partition, long offset, Instant at) {
        cumulativeRows = rows;
        lastSequence = sequence;
        lastPartition = partition;
        lastOffset = offset;
        lastErrorCode = null;
        updatedAt = at;
        status = "COMPLETED";
    }

    public void markIngesting(Instant at) {
        status = "INGESTING";
        lastErrorCode = null;
        updatedAt = at;
    }

    public void recordFailure(String code, Instant at) {
        status = "FAILED";
        lastErrorCode = code;
        updatedAt = at;
    }
}
