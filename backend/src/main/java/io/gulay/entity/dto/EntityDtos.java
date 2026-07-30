package io.gulay.entity.dto;

import io.gulay.entity.data.model.ColumnDataType;
import io.gulay.entity.data.model.EntityStatus;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

public final class EntityDtos {
    public static final String SCHEMA_VERSION = "1.0";

    private EntityDtos() {
    }

    public record EntitySummary(
            String schemaVersion,
            UUID id,
            String name,
            String description,
            EntityStatus status,
            boolean schemaRegistered,
            String latestImportStatus,
            Long governedRowCount,
            Long latestBatchRowCount,
            Instant lastCheckpointAt,
            long version,
            String nameTr,
            String descriptionTr,
            String canonicalName) {
    }

    public record EntityListResponse(
            String schemaVersion, List<EntitySummary> entities,
            int page, int size, long totalElements, long registeredStructureCount, int totalPages,
            boolean first, boolean last) {
    }

    public record ColumnDefinition(
            UUID id,
            @NotBlank
            @Pattern(regexp = "[A-Za-z_][A-Za-z0-9_]*")
            @Size(max = 160)
            String columnName,
            @NotBlank @Size(max = 200) String businessName,
            @NotNull ColumnDataType dataType,
            @Size(max = 4000) String description,
            @Positive int ordinalPosition,
            @Size(max = 200) String businessNameTr,
            @Size(max = 4000) String descriptionTr) {
        public ColumnDefinition(
                UUID id, String columnName, String businessName, ColumnDataType dataType,
                String description, int ordinalPosition) {
            this(id, columnName, businessName, dataType, description, ordinalPosition, null, null);
        }
    }

    public record EntitySchemaResponse(
            String schemaVersion,
            UUID entityId,
            Instant createdAt,
            List<ColumnDefinition> columns) {
    }

    public record ColumnPageResponse(
            String schemaVersion, List<ColumnDefinition> columns,
            int page, int size, long totalElements, int totalPages,
            boolean first, boolean last) {
    }

    public record CreateEntityRequest(
            @NotBlank @Size(max = 160) String name,
            @Size(max = 4000) String description,
            @NotNull EntityStatus status) {
    }

    public record UpdateEntityRequest(
            @NotBlank @Size(max = 160) String name,
            @Size(max = 4000) String description,
            @NotNull EntityStatus status,
            @NotNull Long version) {
    }

    public record StreamEntityDescriptor(
            @NotNull UUID id,
            @NotBlank @Size(max = 160) String name,
            @Size(max = 4000) String description,
            @Size(min = 1, max = 500) List<@Valid ColumnDefinition> columns,
            @Size(max = 160) String nameTr,
            @Size(max = 4000) String descriptionTr) {
        public StreamEntityDescriptor(
                UUID id, String name, String description, List<ColumnDefinition> columns) {
            this(id, name, description, columns, null, null);
        }
    }
}
