package io.gulay.execution.result.data.model;

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
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

@Entity
@Table(name = "execution_result")
@Getter
@Builder
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor(access = AccessLevel.PRIVATE)
public class ExecutionResultModel {
    @Id
    private UUID id;
    @OneToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "execution_id", nullable = false)
    private ExecutionRequestModel execution;
    @Column(name = "schema_version", nullable = false)
    private String schemaVersion;
    @Column(name = "row_count", nullable = false)
    private long rowCount;
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "preview_json", nullable = false, columnDefinition = "jsonb")
    private String previewJson;
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "kpis_json", nullable = false, columnDefinition = "jsonb")
    private String kpisJson;
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "charts_json", nullable = false, columnDefinition = "jsonb")
    private String chartsJson;
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "warnings_json", nullable = false, columnDefinition = "jsonb")
    private String warningsJson;
    @Column(name = "management_summary")
    private String managementSummary;
    @Column(name = "summary_status", nullable = false)
    private String summaryStatus;
    @Column(name = "created_at", nullable = false)
    private Instant createdAt;
}
