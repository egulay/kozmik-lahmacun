package io.gulay.execution.data.service;

import lombok.val;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;
import io.gulay.api.ConflictException;
import io.gulay.api.ForbiddenOperationException;
import io.gulay.configuration.data.service.EffectiveConfigurationService;
import io.gulay.entity.data.repository.BusinessEntityRepository;
import io.gulay.entity.data.service.EntityManagementService;
import io.gulay.entity.dto.EntityDtos;
import io.gulay.execution.ReportPlanningException;
import io.gulay.execution.client.PythonReportPlanningClient;
import io.gulay.execution.data.model.ExecutionCommandOutboxModel;
import io.gulay.execution.data.model.ExecutionRequestModel;
import io.gulay.execution.data.model.ExecutionStatus;
import io.gulay.execution.data.model.ExecutionStatusHistoryModel;
import io.gulay.execution.data.repository.ExecutionCommandOutboxRepository;
import io.gulay.execution.data.repository.ExecutionRequestRepository;
import io.gulay.execution.data.repository.ExecutionStatusHistoryRepository;
import io.gulay.execution.dto.ExecutionDtos;
import io.gulay.execution.messaging.ExecutionMessagingContracts;
import io.gulay.security.PlatformRole;
import io.gulay.user.data.repository.AppUserReferenceRepository;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.HexFormat;
import java.util.Set;
import java.util.UUID;

import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
public class ReportPlanningService {
    private final EntityManagementService entityService;
    private final AppUserReferenceRepository userRepository;
    private final BusinessEntityRepository entityRepository;
    private final ExecutionRequestRepository executionRepository;
    private final ExecutionStatusHistoryRepository historyRepository;
    private final ExecutionCommandOutboxRepository outboxRepository;
    private final PythonReportPlanningClient planningClient;
    private final EffectiveConfigurationService configurationService;
    private final ObjectMapper objectMapper;
    private final Clock clock;

    @Transactional
    public ExecutionDtos.ReportPlanResponse createPending(
            ExecutionDtos.CreateReportPlanRequest request, String idempotencyKey,
            String keycloakUserId, Set<PlatformRole> roles, String correlationId,
            String type) {
        if ("ML".equals(type)
                && !roles.contains(PlatformRole.SCIENTIST)
                && !roles.contains(PlatformRole.ADMIN)) {
            throw new ForbiddenOperationException("ML requires Scientist capability");
        }
        val owner = userRepository.findByKeycloakUserId(keycloakUserId)
                .orElseThrow(() -> new ForbiddenOperationException("Unknown local user"));
        val fingerprint = fingerprint(request, type);
        val existing = executionRepository.findByOwnerIdAndIdempotencyKey(
                owner.getId(), idempotencyKey);
        if (existing.isPresent()) {
            if (!existing.get().getRequestFingerprint().equals(fingerprint)) {
                throw new ConflictException("Idempotency key was already used for another request");
            }
            return response(existing.get());
        }
        val schema = "ML".equals(type)
                ? entityService.authorizedMlSchema(
                request.entityId(), keycloakUserId, roles, request.language())
                : entityService.authorizedReportingSchema(
                request.entityId(), keycloakUserId, roles, request.language());
        val now = Instant.now(clock);
        val execution = executionRepository.save(ExecutionRequestModel.builder()
                .id(UUID.randomUUID()).owner(owner)
                .entity(entityRepository.getReferenceById(request.entityId()))
                .executionType(type).status(ExecutionStatus.PLANNING)
                .originalRequest(request.request()).requestedLanguage(request.language())
                .executionOrderVersion("PENDING").executionOrderJson("{}")
                .authorizationSnapshot(json(objectMapper.createObjectNode()
                        .put("actorUserId", owner.getId().toString())
                        .set("roles", objectMapper.valueToTree(
                                roles.stream().map(Enum::name).sorted().toList()))))
                .configurationSnapshot(json(objectMapper.valueToTree(configurationService.effective())))
                .idempotencyKey(idempotencyKey).requestFingerprint(fingerprint)
                .correlationId(correlationId).requestedAt(now)
                .timeoutAt(now.plusSeconds(configurationService.effective()
                        .execution().timeoutSeconds()))
                .retentionEligibleAt(now.plus(Duration.ofDays(30))).build());
        historyRepository.save(ExecutionStatusHistoryModel.builder()
                .id(UUID.randomUUID()).eventId(UUID.randomUUID()).execution(execution)
                .stage("PLANNING").status(ExecutionStatus.PLANNING).progress(0)
                .messageCode(type + "_PLANNING_STARTED").messageParameters("{}")
                .occurredAt(now).build());
        return response(execution);
    }

    @Transactional
    public ExecutionDtos.ReportPlanResponse completePending(
            UUID executionId, String keycloakUserId, Set<PlatformRole> roles) {
        val execution = executionRepository.findById(executionId)
                .orElseThrow(() -> new ReportPlanningException("Pending execution not found"));
        if (execution.getStatus() != ExecutionStatus.PLANNING) {
            return response(execution);
        }
        val request = new ExecutionDtos.CreateReportPlanRequest(
                execution.getEntity().getId(), execution.getOriginalRequest(),
                execution.getRequestedLanguage());
        val schema = "ML".equals(execution.getExecutionType())
                ? entityService.authorizedMlSchema(
                request.entityId(), keycloakUserId, roles, request.language())
                : entityService.authorizedReportingSchema(
                request.entityId(), keycloakUserId, roles, request.language());
        val planningRequest = planningRequest(
                request, execution.getOwner().getId(), roles,
                execution.getCorrelationId(), schema);
        val result = "ML".equals(execution.getExecutionType())
                ? planningClient.planMl(planningRequest) : planningClient.plan(planningRequest);
        val order = result.path("order");
        validateBinding(order, request, execution.getExecutionType());
        if (!execution.completePlanning("1.0", json(order))) {
            throw new ConflictException("Execution is no longer awaiting planning");
        }
        val now = Instant.now(clock);
        historyRepository.save(ExecutionStatusHistoryModel.builder()
                .id(UUID.randomUUID()).eventId(UUID.randomUUID()).execution(execution)
                .stage("VALIDATING").status(ExecutionStatus.VALIDATED).progress(0)
                .messageCode(execution.getExecutionType() + "_ORDER_VALIDATED")
                .messageParameters("{}").occurredAt(now).build());
        val command = new ExecutionMessagingContracts.ExecutionCommand(
                "1.0", UUID.randomUUID(), execution.getCorrelationId(), execution.getId(),
                execution.getEntity().getId(), execution.getOwner().getId(), now,
                execution.getExecutionType(), execution.getOriginalRequest(),
                SummaryPreference.include(execution.getOriginalRequest()),
                executionSchema(schema), order,
                parse(execution.getAuthorizationSnapshot()),
                parse(execution.getConfigurationSnapshot()));
        outboxRepository.save(ExecutionCommandOutboxModel.builder()
                .id(UUID.randomUUID()).eventId(command.eventId()).execution(execution)
                .payloadJson(json(command)).createdAt(now).attemptCount(0).build());
        return response(execution);
    }

    @Transactional
    public void failPending(UUID executionId, String messageCode) {
        executionRepository.findById(executionId).ifPresent(execution -> {
            if (execution.getStatus() != ExecutionStatus.PLANNING) return;
            val now = Instant.now(clock);
            execution.applyStatus(ExecutionStatus.FAILED, now);
            historyRepository.save(ExecutionStatusHistoryModel.builder()
                    .id(UUID.randomUUID()).eventId(UUID.randomUUID()).execution(execution)
                    .stage("PLANNING").status(ExecutionStatus.FAILED).progress(0)
                    .messageCode(messageCode).messageParameters("{}")
                    .occurredAt(now).build());
        });
    }

    @Transactional
    public ExecutionDtos.ReportPlanResponse create(
            ExecutionDtos.CreateReportPlanRequest request, String idempotencyKey,
            String keycloakUserId, Set<PlatformRole> roles, String correlationId) {
        return createTyped(request, idempotencyKey, keycloakUserId, roles, correlationId, "REPORT");
    }

    @Transactional
    public ExecutionDtos.ReportPlanResponse createMl(
            ExecutionDtos.CreateReportPlanRequest request, String idempotencyKey,
            String keycloakUserId, Set<PlatformRole> roles, String correlationId) {
        if (!roles.contains(PlatformRole.SCIENTIST) && !roles.contains(PlatformRole.ADMIN)) {
            throw new ForbiddenOperationException("ML requires Scientist capability");
        }
        return createTyped(request, idempotencyKey, keycloakUserId, roles, correlationId, "ML");
    }

    private ExecutionDtos.ReportPlanResponse createTyped(
            ExecutionDtos.CreateReportPlanRequest request, String idempotencyKey,
            String keycloakUserId, Set<PlatformRole> roles, String correlationId, String type) {
        val owner = userRepository.findByKeycloakUserId(keycloakUserId)
                .orElseThrow(() -> new ForbiddenOperationException("Unknown local user"));
        val fingerprint = fingerprint(request, type);
        val existing = executionRepository.findByOwnerIdAndIdempotencyKey(owner.getId(), idempotencyKey);
        if (existing.isPresent()) {
            if (!existing.get().getRequestFingerprint().equals(fingerprint)) {
                throw new ConflictException("Idempotency key was already used for another request");
            }
            return response(existing.get());
        }
        val schema = "ML".equals(type)
                ? entityService.authorizedMlSchema(
                request.entityId(), keycloakUserId, roles, request.language())
                : entityService.authorizedReportingSchema(
                request.entityId(), keycloakUserId, roles, request.language());
        val planningRequest = planningRequest(
                request, owner.getId(), roles, correlationId, schema);
        val result = "ML".equals(type)
                ? planningClient.planMl(planningRequest) : planningClient.plan(planningRequest);
        val order = result.path("order");
        validateBinding(order, request, type);
        return persist(request, idempotencyKey, fingerprint, correlationId, owner.getId(),
                roles, schema, order, type);
    }

    private ObjectNode planningRequest(
            ExecutionDtos.CreateReportPlanRequest request, UUID actorId,
            Set<PlatformRole> roles, String correlationId,
            EntityDtos.EntitySchemaResponse schema) {
        val root = objectMapper.createObjectNode();
        root.put("schemaVersion", "1.0").put("requestId", UUID.randomUUID().toString())
                .put("correlationId", correlationId).put("actorUserId", actorId.toString())
                .put("userRequest", request.request()).put("requestedLanguage", request.language());
        val capabilities = root.putArray("capabilities");
        roles.stream().map(Enum::name).sorted().forEach(capabilities::add);
        root.set("authorizedSchema", executionSchema(schema));
        return root;
    }

    private ObjectNode executionSchema(EntityDtos.EntitySchemaResponse schema) {
        val authorized = objectMapper.createObjectNode()
                .put("entityId", schema.entityId().toString());
        val columns = authorized.putArray("columns");
        schema.columns().forEach(column -> {
            val item = columns.addObject();
            item.put("columnName", column.columnName()).put("businessName", column.businessName())
                    .put("dataType", column.dataType().name());
            val values = item.putArray("categoricalValues");
            column.categoricalValues().forEach(values::add);
        });
        return authorized;
    }

    private void validateBinding(JsonNode order, ExecutionDtos.CreateReportPlanRequest request,
                                 String type) {
        if (!order.isObject() || !"1.0".equals(textOrNull(order.path("schemaVersion")))
                || !type.equals(textOrNull(order.path("executionType")))
                || !request.entityId().toString().equals(textOrNull(order.path("entityId")))
                || !request.language().equals(
                        textOrNull(order.path("requestedLanguage")))) {
            throw new ReportPlanningException("Python order does not match the authorized request");
        }
    }

    private String textOrNull(JsonNode node) {
        return node != null && node.isString() ? node.stringValue() : null;
    }

    protected ExecutionDtos.ReportPlanResponse persist(
            ExecutionDtos.CreateReportPlanRequest request, String key, String fingerprint,
            String correlationId, UUID ownerId, Set<PlatformRole> roles,
            EntityDtos.EntitySchemaResponse schema, JsonNode order, String type) {
        val now = Instant.now(clock);
        val execution = executionRepository.save(ExecutionRequestModel.builder()
                .id(UUID.randomUUID()).owner(userRepository.getReferenceById(ownerId))
                .entity(entityRepository.getReferenceById(request.entityId()))
                .executionType(type).status(ExecutionStatus.VALIDATED)
                .originalRequest(request.request()).requestedLanguage(request.language())
                .executionOrderVersion("1.0").executionOrderJson(json(order))
                .authorizationSnapshot(json(objectMapper.createObjectNode()
                        .put("actorUserId", ownerId.toString())
                        .set("roles", objectMapper.valueToTree(
                                roles.stream().map(Enum::name).sorted().toList()))))
                .configurationSnapshot(json(objectMapper.valueToTree(configurationService.effective())))
                .idempotencyKey(key).requestFingerprint(fingerprint)
                .correlationId(correlationId).requestedAt(now)
                .timeoutAt(now.plusSeconds(configurationService.effective()
                        .execution().timeoutSeconds()))
                .retentionEligibleAt(now.plus(java.time.Duration.ofDays(30))).build());
        historyRepository.save(ExecutionStatusHistoryModel.builder()
                .id(UUID.randomUUID()).eventId(UUID.randomUUID()).execution(execution)
                .stage("VALIDATING").status(ExecutionStatus.VALIDATED).progress(0)
                .messageCode(type + "_ORDER_VALIDATED").messageParameters("{}")
                .occurredAt(now).build());
        val command = new ExecutionMessagingContracts.ExecutionCommand(
                "1.0", UUID.randomUUID(), correlationId, execution.getId(),
                request.entityId(), ownerId, now, type, execution.getOriginalRequest(),
                SummaryPreference.include(execution.getOriginalRequest()),
                executionSchema(schema), order,
                parse(execution.getAuthorizationSnapshot()),
                parse(execution.getConfigurationSnapshot()));
        outboxRepository.save(ExecutionCommandOutboxModel.builder()
                .id(UUID.randomUUID()).eventId(command.eventId()).execution(execution)
                .payloadJson(json(command)).createdAt(now).attemptCount(0).build());
        return response(execution);
    }

    private ExecutionDtos.ReportPlanResponse response(ExecutionRequestModel execution) {
        try {
            return new ExecutionDtos.ReportPlanResponse("1.0", execution.getId(),
                    execution.getExecutionType(), execution.getStatus().name(),
                    execution.getEntity().getId(), execution.getRequestedAt(),
                    objectMapper.readTree(execution.getExecutionOrderJson()));
        } catch (Exception exception) {
            throw new IllegalStateException("Stored execution order is invalid", exception);
        }
    }

    private String json(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (Exception exception) {
            throw new IllegalStateException("Could not serialize planning snapshot", exception);
        }
    }

    private JsonNode parse(String value) {
        try {
            return objectMapper.readTree(value);
        } catch (Exception exception) {
            throw new IllegalStateException("Could not parse planning snapshot", exception);
        }
    }

    private String fingerprint(ExecutionDtos.CreateReportPlanRequest request, String type) {
        try {
            val canonical = type + "\n" + request.entityId() + "\n"
                    + request.language() + "\n" + request.request();
            return HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256").digest(canonical.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception exception) {
            throw new IllegalStateException(exception);
        }
    }
}
