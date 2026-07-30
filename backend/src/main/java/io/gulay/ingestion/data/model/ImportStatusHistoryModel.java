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
@Table(name = "import_status_history")
@Getter
@Builder
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor(access = AccessLevel.PRIVATE)
public class ImportStatusHistoryModel {
    @Id
    private UUID id;
    @Column(name = "event_id", nullable = false, unique = true)
    private UUID eventId;
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "import_job_id", nullable = false)
    private ImportJobModel importJob;
    @Column(nullable = false)
    private String stage;
    @Column(nullable = false)
    private String status;
    @Column(name = "message_code", nullable = false)
    private String messageCode;
    @Column(name = "occurred_at", nullable = false)
    private Instant occurredAt;
}
