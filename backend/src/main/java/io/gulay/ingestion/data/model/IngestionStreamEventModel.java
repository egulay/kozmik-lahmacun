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
import lombok.NoArgsConstructor;

@Entity
@Table(name = "ingestion_stream_event")
@Builder
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor(access = AccessLevel.PRIVATE)
public class IngestionStreamEventModel {
    @Id
    @Column(name = "event_id")
    private UUID eventId;
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "stream_id", nullable = false)
    private IngestionStreamModel stream;
    @Column(name = "chunk_id", nullable = false)
    private UUID chunkId;
    @Column(nullable = false)
    private String stage;
    @Column(name = "message_code", nullable = false)
    private String messageCode;
    @Column(name = "occurred_at", nullable = false)
    private Instant occurredAt;
}
