package io.gulay.execution.data.model;

import io.gulay.ingestion.data.model.IngestionStreamModel;
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
@Table(name = "execution_stream_binding")
@Getter
@Builder
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor(access = AccessLevel.PRIVATE)
public class ExecutionStreamBindingModel {
    @Id
    private UUID executionId;
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "stream_id", nullable = false)
    private IngestionStreamModel stream;
    @Column(name = "through_sequence", nullable = false)
    private long throughSequence;
    @Column(name = "through_offset", nullable = false)
    private long throughOffset;
    @Column(name = "snapshot_row_count", nullable = false)
    private long snapshotRowCount;
    @Column(name = "resolved_at", nullable = false)
    private Instant resolvedAt;
}
