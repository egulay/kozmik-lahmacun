package io.gulay.entity.data.service;

import lombok.val;

import io.gulay.api.ConflictException;
import io.gulay.api.ForbiddenOperationException;
import io.gulay.api.ResourceNotFoundException;
import io.gulay.entity.data.model.BusinessEntityModel;
import io.gulay.entity.data.model.EntityColumnModel;
import io.gulay.entity.data.model.EntityColumnCategoryValueModel;
import io.gulay.entity.data.model.EntityStatus;
import io.gulay.entity.data.repository.BusinessEntityRepository;
import io.gulay.entity.data.repository.EntityColumnRepository;
import io.gulay.entity.data.repository.EntityColumnCategoryValueRepository;
import io.gulay.entity.dto.EntityDtos;
import io.gulay.entity.dto.EntityDtos.ColumnDefinition;
import io.gulay.ingestion.data.repository.ImportJobRepository;
import io.gulay.ingestion.data.repository.IngestionStreamBatchRepository;
import io.gulay.ingestion.data.repository.IngestionStreamRepository;
import io.gulay.security.PlatformRole;
import io.gulay.user.data.model.UserRole;
import io.gulay.user.data.model.UserStatus;
import io.gulay.user.data.model.AppUserReferenceModel;
import io.gulay.user.data.repository.AppUserReferenceRepository;

import java.time.Clock;
import java.time.Instant;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;

import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Entity UUID is the immutable data-structure identity. There is exactly one
 * registered column definition per entity; a structural change requires a new
 * entity UUID.
 */
@Service
@RequiredArgsConstructor
public class EntityManagementService {
    private final BusinessEntityRepository entityRepository;
    private final EntityColumnRepository columnRepository;
    private final EntityColumnCategoryValueRepository categoryValueRepository;
    private final ImportJobRepository importJobRepository;
    private final IngestionStreamRepository ingestionStreamRepository;
    private final IngestionStreamBatchRepository ingestionStreamBatchRepository;
    private final AppUserReferenceRepository userRepository;
    private final io.gulay.entity.data.repository.EntityDeletionRepository deletionRepository;
    private final Clock clock;

    @Value("${kozmik.ingestion.system-keycloak-user-id:aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa3}")
    private String ingestionSystemKeycloakUserId;

    @Transactional(readOnly = true)
    public EntityDtos.EntityListResponse list(
            String keycloakUserId, Set<PlatformRole> roles) {
        return list(keycloakUserId, roles, 0, 100, "en");
    }

    @Transactional(readOnly = true)
    public EntityDtos.EntityListResponse list(
            String keycloakUserId, Set<PlatformRole> roles, String language) {
        return list(keycloakUserId, roles, 0, 100, language);
    }

    @Transactional(readOnly = true)
    public EntityDtos.EntityListResponse list(
            String keycloakUserId, Set<PlatformRole> roles, int page, int size) {
        return list(keycloakUserId, roles, page, size, "en");
    }

    @Transactional(readOnly = true)
    public EntityDtos.EntityListResponse list(
            String keycloakUserId, Set<PlatformRole> roles, int page, int size,
            String language) {
        user(keycloakUserId);
        val pageable = PageRequest.of(page, size, Sort.by("name").ascending());
        val entities = roles.contains(PlatformRole.ADMIN)
                ? entityRepository.findByStatusNot(EntityStatus.DELETION_PENDING, pageable)
                : entityRepository.findByStatus(EntityStatus.ACTIVE, pageable);
        val summaries = entities.stream().map(entity -> summary(entity, language)).toList();
        return new EntityDtos.EntityListResponse(
                EntityDtos.SCHEMA_VERSION, summaries, entities.getNumber(),
                entities.getSize(), entities.getTotalElements(),
                entityRepository.countWithRegisteredSchema(), entities.getTotalPages(),
                entities.isFirst(), entities.isLast());
    }

    @Transactional(readOnly = true)
    public EntityDtos.EntitySummary get(
            UUID entityId, String keycloakUserId, Set<PlatformRole> roles) {
        return get(entityId, keycloakUserId, roles, "en");
    }

    @Transactional(readOnly = true)
    public EntityDtos.EntitySummary get(
            UUID entityId, String keycloakUserId, Set<PlatformRole> roles, String language) {
        return summary(authorizedEntity(entityId, keycloakUserId, roles), language);
    }

    @Transactional(readOnly = true)
    public EntityDtos.EntitySchemaResponse currentSchema(
            UUID entityId, String keycloakUserId, Set<PlatformRole> roles) {
        return currentSchema(entityId, keycloakUserId, roles, "en");
    }

    @Transactional(readOnly = true)
    public EntityDtos.EntitySchemaResponse currentSchema(
            UUID entityId, String keycloakUserId, Set<PlatformRole> roles, String language) {
        return schema(authorizedEntity(entityId, keycloakUserId, roles), language);
    }

    @Transactional(readOnly = true)
    public EntityDtos.ColumnPageResponse currentSchemaColumns(
            UUID entityId, String keycloakUserId, Set<PlatformRole> roles,
            int page, int size, String language) {
        val entity = authorizedEntity(entityId, keycloakUserId, roles);
        requireSchema(entity);
        val columns = columnRepository.findByEntityId(
                entity.getId(), PageRequest.of(page, size, Sort.by("ordinalPosition")));
        return new EntityDtos.ColumnPageResponse(
                EntityDtos.SCHEMA_VERSION,
                columns.stream().map(column -> columnDefinition(column, language)).toList(),
                columns.getNumber(), columns.getSize(), columns.getTotalElements(),
                columns.getTotalPages(), columns.isFirst(), columns.isLast());
    }

    @Transactional(readOnly = true)
    public EntityDtos.EntitySchemaResponse authorizedReportingSchema(
            UUID entityId, String keycloakUserId, Set<PlatformRole> roles, String language) {
        return currentSchema(entityId, keycloakUserId, roles, language);
    }

    @Transactional(readOnly = true)
    public EntityDtos.EntitySchemaResponse authorizedMlSchema(
            UUID entityId, String keycloakUserId, Set<PlatformRole> roles, String language) {
        if (!roles.contains(PlatformRole.SCIENTIST) && !roles.contains(PlatformRole.ADMIN)) {
            throw new ForbiddenOperationException("ML requires Scientist capability");
        }
        return currentSchema(entityId, keycloakUserId, roles, language);
    }

    @Transactional(readOnly = true)
    public EntityDtos.EntitySchemaResponse internalSchema(
            UUID entityId, UUID actorUserId, PlatformRole capability) {
        val actor = userRepository.findById(actorUserId)
                .orElseThrow(() -> new ForbiddenOperationException(
                        "Unknown authorization actor"));
        if (actor.getStatus() != UserStatus.ACTIVE
                || !hasCapability(actor.getRoles(), capability)) {
            throw new ForbiddenOperationException("Actor is not authorized for this capability");
        }
        return schema(activeEntity(entityId));
    }

    private boolean hasCapability(Set<UserRole> roles, PlatformRole capability) {
        return switch (capability) {
            case REPORTER -> roles.contains(UserRole.REPORTER)
                    || roles.contains(UserRole.SCIENTIST) || roles.contains(UserRole.ADMIN);
            case SCIENTIST -> roles.contains(UserRole.SCIENTIST) || roles.contains(UserRole.ADMIN);
            case ADMIN -> roles.contains(UserRole.ADMIN);
        };
    }

    @Transactional(readOnly = true)
    public EntityDtos.EntitySchemaResponse internalIngestionSchema(UUID entityId) {
        return schema(activeEntity(entityId));
    }

    @Transactional
    public EntityDtos.EntitySchemaResponse resolveOrRegisterStreamEntity(
            EntityDtos.StreamEntityDescriptor descriptor) {
        if (deletionRepository.tombstoned(descriptor.id())) {
            throw new ConflictException("Entity UUID was retired and cannot be ingested again; use a new UUID");
        }
        validateColumns(descriptor.columns());
        val existing = entityRepository.findById(descriptor.id());
        if (existing.isPresent()) {
            val entity = existing.get();
            if (!entity.getName().equalsIgnoreCase(descriptor.name().trim())) {
                throw new ConflictException(
                        "Entity UUID is already registered with a different structure");
            }
            if (!columnRepository.existsByEntityId(entity.getId())) {
                descriptor.columns().forEach(column -> saveColumn(entity, column));
                localize(entity, descriptor);
                return schema(entity);
            }
            if (!sameSchema(schema(entity).columns(), descriptor.columns())) {
                throw new ConflictException(
                        "Entity UUID is already registered with a different structure");
            }
            localize(entity, descriptor);
            mergeCategoricalValues(entity, descriptor.columns());
            return schema(entity);
        }
        if (entityRepository.existsByNameIgnoreCase(descriptor.name())) {
            throw new ConflictException("Data entity name is already registered");
        }
        val now = Instant.now(clock);
        val actor = user(ingestionSystemKeycloakUserId);
        val entity = entityRepository.save(BusinessEntityModel.builder()
                .id(descriptor.id()).name(descriptor.name().trim())
                .description(descriptor.description())
                .nameTr(descriptor.nameTr()).descriptionTr(descriptor.descriptionTr())
                .status(EntityStatus.ACTIVE)
                .createdBy(actor).createdAt(now).updatedAt(now).build());
        descriptor.columns().forEach(column -> saveColumn(entity, column));
        return schema(entity);
    }

    @Transactional
    public EntityDtos.EntitySchemaResponse updateCategoricalVocabulary(
            UUID entityId, EntityDtos.CategoricalVocabularyUpdate request) {
        val entity = activeEntity(entityId);
        val supplied = request.columns().stream().collect(java.util.stream.Collectors.toMap(
                EntityDtos.ColumnVocabulary::columnName,
                EntityDtos.ColumnVocabulary::values,
                (left, right) -> right));
        val columns = columnRepository.findByEntityIdOrderByOrdinalPosition(entityId);
        val registeredNames = columns.stream().map(EntityColumnModel::getColumnName)
                .collect(java.util.stream.Collectors.toSet());
        if (!registeredNames.containsAll(supplied.keySet())) {
            throw new ConflictException("Categorical vocabulary references an unknown column");
        }
        for (val column : columns) {
            val values = supplied.get(column.getColumnName());
            if (values != null) {
                if (column.getDataType() != io.gulay.entity.data.model.ColumnDataType.STRING) {
                    throw new ConflictException(
                            "Categorical vocabulary requires a STRING column");
                }
                mergeCategoricalValues(column, values);
            }
        }
        return schema(entity);
    }

    @Transactional
    public EntityDtos.EntitySummary create(
            EntityDtos.CreateEntityRequest request, String actorKeycloakId) {
        if (entityRepository.existsByNameIgnoreCase(request.name())) {
            throw new ConflictException("A data entity with this name already exists");
        }
        val now = Instant.now(clock);
        return summary(entityRepository.save(BusinessEntityModel.builder()
                .id(UUID.randomUUID()).name(request.name().trim())
                .description(request.description()).status(request.status())
                .createdBy(user(actorKeycloakId)).createdAt(now).updatedAt(now).build()));
    }

    @Transactional
    public EntityDtos.EntitySummary update(
            UUID entityId, EntityDtos.UpdateEntityRequest request) {
        val entity = entityRepository.findById(entityId)
                .orElseThrow(() -> new ResourceNotFoundException("Entity not found"));
        if (entity.getVersion() != request.version()) {
            throw new ConflictException("Entity was modified by another request");
        }
        entity.update(request.name().trim(), request.description(), request.status(),
                Instant.now(clock));
        return summary(entityRepository.save(entity));
    }

    private BusinessEntityModel authorizedEntity(
            UUID entityId, String keycloakUserId, Set<PlatformRole> roles) {
        user(keycloakUserId);
        val entity = entityRepository.findById(entityId)
                .orElseThrow(() -> new ResourceNotFoundException("Entity not found"));
        if (entity.getStatus() != EntityStatus.ACTIVE && !roles.contains(PlatformRole.ADMIN)) {
            throw new ForbiddenOperationException("Entity is not active");
        }
        return entity;
    }

    private BusinessEntityModel activeEntity(UUID entityId) {
        return entityRepository.findById(entityId)
                .filter(entity -> entity.getStatus() == EntityStatus.ACTIVE)
                .orElseThrow(() -> new ResourceNotFoundException("Active data entity not found"));
    }

    private AppUserReferenceModel user(String keycloakId) {
        return userRepository.findByKeycloakUserId(keycloakId)
                .orElseThrow(() -> new ForbiddenOperationException(
                        "Authenticated user has no local control-plane reference"));
    }

    private void requireSchema(BusinessEntityModel entity) {
        if (!columnRepository.existsByEntityId(entity.getId())) {
            throw new ResourceNotFoundException("No structure is registered for this data entity");
        }
    }

    private EntityDtos.EntitySchemaResponse schema(BusinessEntityModel entity) {
        requireSchema(entity);
        return new EntityDtos.EntitySchemaResponse(
                EntityDtos.SCHEMA_VERSION, entity.getId(), entity.getCreatedAt(),
                columnRepository.findByEntityIdOrderByOrdinalPosition(entity.getId())
                        .stream().map(this::columnDefinition).toList());
    }

    private EntityDtos.EntitySchemaResponse schema(
            BusinessEntityModel entity, String language) {
        requireSchema(entity);
        return new EntityDtos.EntitySchemaResponse(
                EntityDtos.SCHEMA_VERSION, entity.getId(), entity.getCreatedAt(),
                columnRepository.findByEntityIdOrderByOrdinalPosition(entity.getId())
                        .stream().map(column -> columnDefinition(column, language)).toList());
    }

    private void validateColumns(List<ColumnDefinition> columns) {
        val names = new HashSet<String>();
        val ordinals = new HashSet<Integer>();
        for (val column : columns) {
            if (!names.add(column.columnName().toLowerCase())) {
                throw new ConflictException("Column names must be unique");
            }
            if (!ordinals.add(column.ordinalPosition())) {
                throw new ConflictException("Column ordinal positions must be unique");
            }
        }
    }

    private boolean sameSchema(List<ColumnDefinition> registered, List<ColumnDefinition> supplied) {
        if (registered.size() != supplied.size()) return false;
        for (int index = 0; index < registered.size(); index++) {
            val left = registered.get(index);
            val right = supplied.get(index);
            if (!left.columnName().equals(right.columnName())
                    || left.dataType() != right.dataType()
                    || left.ordinalPosition() != right.ordinalPosition()) {
                return false;
            }
        }
        return true;
    }

    private EntityColumnModel toColumn(
            BusinessEntityModel entity, ColumnDefinition column) {
        return EntityColumnModel.builder()
                .id(UUID.randomUUID()).entity(entity)
                .columnName(column.columnName()).businessName(column.businessName())
                .businessNameTr(column.businessNameTr())
                .dataType(column.dataType()).description(column.description())
                .descriptionTr(column.descriptionTr())
                .ordinalPosition(column.ordinalPosition()).build();
    }

    private void saveColumn(BusinessEntityModel entity, ColumnDefinition definition) {
        val column = columnRepository.save(toColumn(entity, definition));
        mergeCategoricalValues(column, definition.categoricalValues());
    }

    private void mergeCategoricalValues(
            BusinessEntityModel entity, List<ColumnDefinition> definitions) {
        val supplied = definitions.stream().collect(java.util.stream.Collectors.toMap(
                ColumnDefinition::columnName, ColumnDefinition::categoricalValues));
        columnRepository.findByEntityIdOrderByOrdinalPosition(entity.getId()).forEach(column ->
                mergeCategoricalValues(column, supplied.getOrDefault(
                        column.getColumnName(), List.of())));
    }

    private void mergeCategoricalValues(EntityColumnModel column, List<String> supplied) {
        if (column.getDataType() != io.gulay.entity.data.model.ColumnDataType.STRING
                || supplied == null || supplied.isEmpty()) return;
        val normalized = supplied.stream().map(String::trim).filter(value -> !value.isEmpty())
                .distinct().sorted().toList();
        val existing = categoryValueRepository.findByColumnIdOrderByValueAsc(column.getId())
                .stream().map(EntityColumnCategoryValueModel::getValue).collect(
                        java.util.stream.Collectors.toSet());
        val combined = new HashSet<>(existing);
        combined.addAll(normalized);
        if (combined.size() > 32) {
            throw new ConflictException("Categorical vocabulary exceeds the governed limit");
        }
        normalized.stream()
                .filter(value -> !existing.contains(value))
                .forEach(value -> categoryValueRepository.save(
                        EntityColumnCategoryValueModel.builder().id(UUID.randomUUID())
                                .column(column).value(value).build()));
    }

    private void localize(
            BusinessEntityModel entity, EntityDtos.StreamEntityDescriptor descriptor) {
        if (descriptor.nameTr() != null && !descriptor.nameTr().isBlank()) {
            entity.localize(descriptor.nameTr(), descriptor.descriptionTr(), Instant.now(clock));
        }
        val registered = columnRepository.findByEntityIdOrderByOrdinalPosition(entity.getId());
        for (var index = 0; index < registered.size(); index++) {
            val supplied = descriptor.columns().get(index);
            if (supplied.businessNameTr() != null && !supplied.businessNameTr().isBlank()) {
                registered.get(index).localize(
                        supplied.businessNameTr(), supplied.descriptionTr());
            }
        }
    }

    private ColumnDefinition columnDefinition(EntityColumnModel column) {
        return columnDefinition(column, "en");
    }

    private ColumnDefinition columnDefinition(EntityColumnModel column, String language) {
        val turkish = language != null && language.toLowerCase().startsWith("tr");
        return new ColumnDefinition(
                column.getId(), column.getColumnName(),
                turkish && column.getBusinessNameTr() != null
                        ? column.getBusinessNameTr() : column.getBusinessName(),
                column.getDataType(),
                turkish && column.getDescriptionTr() != null
                        ? column.getDescriptionTr() : column.getDescription(),
                column.getOrdinalPosition(), column.getBusinessNameTr(),
                column.getDescriptionTr(),
                categoryValueRepository.findByColumnIdOrderByValueAsc(column.getId())
                        .stream().map(EntityColumnCategoryValueModel::getValue).toList());
    }

    private EntityDtos.EntitySummary summary(BusinessEntityModel entity) {
        return summary(entity, "en");
    }

    private EntityDtos.EntitySummary summary(BusinessEntityModel entity, String language) {
        val latestImport = importJobRepository.findFirstByEntityIdOrderByCreatedAtDesc(entity.getId());
        val completedImport = importJobRepository.findFirstByEntityIdAndStatusOrderByCompletedAtDesc(
                entity.getId(), "COMPLETED");
        val latestStream = ingestionStreamRepository.findFirstByEntityIdOrderByUpdatedAtDesc(
                entity.getId());
        val useStream = latestStream.isPresent() && latestImport.map(job -> {
            val importTime = job.getCompletedAt() == null ? job.getCreatedAt() : job.getCompletedAt();
            return !latestStream.get().getUpdatedAt().isBefore(importTime);
        }).orElse(true);

        String status = null;
        Long rows = null;
        Long batchRows = null;
        Instant checkpoint = null;
        if (useStream) {
            val stream = latestStream.orElseThrow();
            val batch = ingestionStreamBatchRepository
                    .findFirstByStreamIdAndStatusOrderBySequenceNumberDesc(
                            stream.getId(), "COMPLETED");
            status = stream.getStatus();
            rows = stream.getCumulativeRows();
            batchRows = batch.map(value -> value.getRowCount()).orElse(null);
            checkpoint = batch.map(value -> value.getCompletedAt()).orElse(null);
        } else if (latestImport.isPresent()) {
            val latest = latestImport.orElseThrow();
            val completed = "COMPLETED".equals(latest.getStatus())
                    ? latest : completedImport.orElse(null);
            status = latest.getStatus();
            rows = completed == null ? null : completed.getRowCount();
            batchRows = rows;
            checkpoint = completed == null ? null : completed.getCompletedAt();
        }
        val turkish = language != null && language.toLowerCase().startsWith("tr");
        return new EntityDtos.EntitySummary(
                EntityDtos.SCHEMA_VERSION, entity.getId(),
                turkish && entity.getNameTr() != null ? entity.getNameTr() : entity.getName(),
                turkish && entity.getDescriptionTr() != null
                        ? entity.getDescriptionTr() : entity.getDescription(),
                entity.getStatus(),
                columnRepository.existsByEntityId(entity.getId()),
                status, rows, batchRows, checkpoint, entity.getVersion(),
                entity.getNameTr(), entity.getDescriptionTr(), entity.getName());
    }
}
