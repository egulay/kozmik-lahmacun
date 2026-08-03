package io.gulay.execution.messaging;

import lombok.val;

import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.JsonNode;
import io.gulay.execution.data.model.ExecutionStatus;
import io.gulay.execution.data.model.ExecutionStatusHistoryModel;
import io.gulay.execution.data.model.ProcessedExecutionEventModel;
import io.gulay.execution.data.repository.ExecutionRequestRepository;
import io.gulay.execution.data.repository.ExecutionStatusHistoryRepository;
import io.gulay.execution.data.repository.ProcessedExecutionEventRepository;
import io.gulay.execution.failure.data.model.ExecutionFailureModel;
import io.gulay.execution.failure.data.repository.ExecutionFailureRepository;
import io.gulay.execution.result.data.model.ExecutionArtifactModel;
import io.gulay.execution.result.data.model.ExecutionResultModel;
import io.gulay.execution.result.data.repository.ExecutionArtifactRepository;
import io.gulay.execution.result.data.repository.ExecutionResultRepository;

import java.time.Clock;
import java.time.Instant;
import java.util.Set;
import java.util.UUID;

import lombok.RequiredArgsConstructor;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Component
@RequiredArgsConstructor
public class ExecutionEventConsumer {
    private static final Set<String> STAGES = Set.of(
            "QUEUED", "PREPARING", "VALIDATING", "RESOLVING_DATA", "TUNING",
            "RUNNING", "TRAINING",
            "WRITING_RESULTS", "SUMMARIZING", "COMPLETED", "FAILED",
            "CANCELLED", "TIMED_OUT");
    private static final Set<String> SAFE_CODES = Set.of(
            "EXECUTION_QUEUED", "EXECUTION_PREPARING", "EXECUTION_VALIDATING",
            "EXECUTION_ORDER_INVALID",
            "SCHEMA_VERSION_MISMATCH", "EXECUTION_TIMEOUT", "EXECUTION_CANCELLED",
            "EXECUTION_WORKER_FAILED", "EXECUTION_SPARK_RUNNING",
            "EXECUTION_RESOLVING_DATA", "GOVERNED_DATASET_NOT_FOUND",
            "GOVERNED_DATASET_BINDING_MISMATCH",
            "EXECUTION_ML_TUNING",
            "EXECUTION_WRITING_RESULTS", "EXECUTION_SUMMARIZING",
            "EXECUTION_REPORT_COMPLETED", "EXECUTION_RESULT_READY",
            "SPARK_JOB_FAILED", "SPARK_RUNTIME_UNAVAILABLE",
            "ML_TUNING_CONFIGURATION_UNSAFE",
            "ARTIFACT_WRITE_FAILED", "EXECUTION_ML_TRAINING");


    private final ObjectMapper objectMapper;
    private final KafkaMessageSigner signer;
    private final ExecutionRequestRepository executions;
    private final ExecutionStatusHistoryRepository history;
    private final ProcessedExecutionEventRepository processed;
    private final ExecutionFailureRepository failures;
    private final ExecutionResultRepository results;
    private final ExecutionArtifactRepository artifacts;
    private final ExecutionEventHub hub;
    private final Clock clock;

    @KafkaListener(topics = "${kozmik.kafka.event-topic:execution.events.v1}")
    @Transactional
    public void status(String payload) throws Exception {
        val unwrapped = signer.unwrap(payload);
        val node = objectMapper.readTree(unwrapped);
        if ("DELETE_ARTIFACT".equals(textOrNull(node.path("operation")))) {
            applyArtifactRetention(objectMapper.readValue(
                    unwrapped, ExecutionMessagingContracts.ArtifactRetentionEvent.class));
            return;
        }
        apply(objectMapper.readValue(
                unwrapped, ExecutionMessagingContracts.ExecutionStatusEvent.class));
    }

    @KafkaListener(topics = "${kozmik.kafka.result-topic:execution.results.v1}")
    @Transactional
    public void result(String payload) throws Exception {
        val event = objectMapper.readValue(signer.unwrap(payload),
                ExecutionMessagingContracts.ExecutionResultNotification.class);
        applyResult(event);
    }

    @Transactional
    public void apply(ExecutionMessagingContracts.ExecutionStatusEvent event) {
        requireEnvelope(event.schemaVersion(), event.eventId(), event.correlationId(),
                event.executionId(), event.entityId());
        if (!STAGES.contains(event.stage()) || !SAFE_CODES.contains(event.messageCode())
                || event.progressPercent() < 0 || event.progressPercent() > 100
                || event.details().toString().length() > 4000) {
            throw new IllegalArgumentException("Unsafe execution status event");
        }
        if (processed.existsById(event.eventId())) {
            return;
        }
        val execution = executions.findById(event.executionId())
                .orElseThrow(() -> new IllegalArgumentException("Unknown execution"));
        if (!execution.getEntity().getId().equals(event.entityId())
                || !execution.getOwner().getId().equals(event.actorUserId())) {
            throw new IllegalArgumentException("Execution event binding mismatch");
        }
        val status = ExecutionStatus.valueOf(event.status());
        if (!execution.applyStatus(status, event.occurredAt())) {
            processed.save(ProcessedExecutionEventModel.builder()
                    .eventId(event.eventId()).eventType("IGNORED_TERMINAL_STATUS")
                    .execution(execution).processedAt(Instant.now(clock)).build());
            return;
        }
        history.save(ExecutionStatusHistoryModel.builder()
                .id(UUID.randomUUID()).eventId(event.eventId()).execution(execution)
                .stage(event.stage()).status(status).progress(event.progressPercent())
                .messageCode(event.messageCode())
                .messageParameters(json(event.details())).occurredAt(event.occurredAt()).build());
        if (status == ExecutionStatus.FAILED && event.details().hasNonNull("failureCode")) {
            persistFailure(execution, event);
        }
        processed.save(ProcessedExecutionEventModel.builder()
                .eventId(event.eventId()).eventType("STATUS").execution(execution)
                .processedAt(Instant.now(clock)).build());
        afterCommit(execution.getId(), execution.getOwner().getKeycloakUserId(),
                event.eventId(), status == ExecutionStatus.FAILED
                ? "execution-failed" : "execution-status-changed", event);
    }

    private void persistFailure(
            io.gulay.execution.data.model.ExecutionRequestModel execution,
            ExecutionMessagingContracts.ExecutionStatusEvent event) {
        val details = event.details();
        val schemaVersion = bounded(details, "schemaVersion", 20);
        val failureCode = bounded(details, "failureCode", 100);
        val failedStage = bounded(details, "failedStage", 100);
        val technicalReason = bounded(details, "technicalReason", 1000);
        val userExplanation = bounded(details, "userExplanation", 2000);
        val explanationStatus = bounded(details, "explanationStatus", 20);
        val language = bounded(details, "language", 2);
        if (!failureCode.matches("[A-Z0-9_]{1,100}")
                || !failedStage.matches("[A-Z0-9_]{1,100}")
                || !Set.of("COMPLETED", "FAILED").contains(explanationStatus)
                || !Set.of("tr", "en").contains(language)
                || details.path("retryable").isMissingNode()
                || !details.path("retryable").isBoolean()) {
            throw new IllegalArgumentException("Unsafe execution failure details");
        }
        if (failures.findByExecutionId(execution.getId()).isEmpty()) {
            failures.save(ExecutionFailureModel.builder()
                    .id(UUID.randomUUID()).execution(execution)
                    .schemaVersion(schemaVersion).failureCode(failureCode)
                    .failedStage(failedStage)
                    .sanitizedTechnicalReason(technicalReason)
                    .userExplanation(userExplanation)
                    .explanationStatus(explanationStatus)
                    .retryable(details.path("retryable").asBoolean())
                    .language(language).createdAt(event.occurredAt()).build());
        }
    }

    private String bounded(JsonNode details, String field, int maximumLength) {
        val value = textOrNull(details.path(field));
        if (value == null) {
            return null;
        }
        if (value.isBlank() || value.length() > maximumLength) {
            throw new IllegalArgumentException("Unsafe execution failure details");
        }
        return value;
    }

    private String textOrNull(JsonNode node) {
        return node != null && node.isString() ? node.stringValue() : null;
    }

    @Transactional
    public void applyResult(ExecutionMessagingContracts.ExecutionResultNotification event) {
        requireEnvelope(event.schemaVersion(), event.eventId(), event.correlationId(),
                event.executionId(), event.entityId());
        if (!SAFE_CODES.contains(event.resultCode()) || event.rowCount() < 0
                || event.preview() == null || event.kpis() == null || event.charts() == null
                || event.warnings() == null || event.artifact() == null
                || !"PARQUET".equals(event.artifact().format())
                || !"results".equals(event.artifact().bucket())
                || !event.artifact().objectKey().matches(
                "^executions/" + event.executionId() + "/[A-Za-z0-9._/-]{1,800}$")
                || event.preview().toString().length() > 200_000
                || event.kpis().toString().length() > 20_000
                || event.charts().toString().length() > 100_000
                || event.warnings().toString().length() > 20_000
                || !Set.of("COMPLETED", "FAILED", "SKIPPED").contains(event.summaryStatus())
                || invalidAuditText(event.summaryProvider(), 100)
                || invalidAuditText(event.summaryProviderModel(), 200)
                || event.summaryGeneratedAt() == null
                || "COMPLETED".equals(event.summaryStatus())
                && (event.resultSummary() == null || event.resultSummary().isBlank())
                || "COMPLETED".equals(event.summaryStatus())
                && event.summaryErrorCode() != null
                || "FAILED".equals(event.summaryStatus())
                && (event.resultSummary() != null
                || invalidAuditText(event.summaryErrorCode(), 100))
                || "SKIPPED".equals(event.summaryStatus())
                && (event.resultSummary() != null || event.summaryErrorCode() != null
                || !"NOT_REQUESTED".equals(event.summaryProvider())
                || !"NOT_REQUESTED".equals(event.summaryProviderModel()))) {
            throw new IllegalArgumentException("Unsafe execution result event");
        }
        if (processed.existsById(event.eventId())) {
            return;
        }
        val execution = executions.findById(event.executionId())
                .orElseThrow(() -> new IllegalArgumentException("Unknown execution"));
        if (!execution.getEntity().getId().equals(event.entityId())
                || !execution.getOwner().getId().equals(event.actorUserId())) {
            throw new IllegalArgumentException("Execution result binding mismatch");
        }
        val result = results.save(ExecutionResultModel.builder().id(UUID.randomUUID())
                .execution(execution).schemaVersion(event.schemaVersion()).rowCount(event.rowCount())
                .previewJson(json(event.preview())).kpisJson(json(event.kpis()))
                .chartsJson(json(event.charts())).warningsJson(json(event.warnings()))
                .summaryStatus(event.summaryStatus())
                .resultSummary(event.resultSummary())
                .summaryProvider(event.summaryProvider())
                .summaryProviderModel(event.summaryProviderModel())
                .summaryGeneratedAt(event.summaryGeneratedAt())
                .summaryErrorCode(event.summaryErrorCode())
                .createdAt(event.occurredAt()).build());
        artifacts.save(ExecutionArtifactModel.builder().id(event.artifact().artifactId()).result(result)
                .format(event.artifact().format()).bucketName(event.artifact().bucket())
                .objectKey(event.artifact().objectKey()).sizeBytes(event.artifact().sizeBytes())
                .createdAt(event.occurredAt()).build());
        if (event.modelArtifact() != null) {
            if (!"SPARK_ML_ZIP".equals(event.modelArtifact().format())
                    || !"models".equals(event.modelArtifact().bucket())
                    || !event.modelArtifact().objectKey().matches(
                    "^executions/" + event.executionId() + "/[A-Za-z0-9._/-]{1,800}$")) {
                throw new IllegalArgumentException("Unsafe model artifact");
            }
            artifacts.save(ExecutionArtifactModel.builder().id(event.modelArtifact().artifactId())
                    .result(result).format(event.modelArtifact().format())
                    .bucketName(event.modelArtifact().bucket())
                    .objectKey(event.modelArtifact().objectKey())
                    .sizeBytes(event.modelArtifact().sizeBytes())
                    .createdAt(event.occurredAt()).build());
        }
        processed.save(ProcessedExecutionEventModel.builder().eventId(event.eventId())
                .eventType("RESULT").execution(execution).processedAt(Instant.now(clock)).build());
        afterCommit(execution.getId(), execution.getOwner().getKeycloakUserId(),
                event.eventId(), "execution-result-ready", event);
    }

    @Transactional
    public void applyArtifactRetention(
            ExecutionMessagingContracts.ArtifactRetentionEvent event) {
        requireEnvelope(event.schemaVersion(), event.eventId(), event.correlationId(),
                event.executionId(), event.entityId());
        if (!"DELETE_ARTIFACT".equals(event.operation())
                || !Set.of("SUCCEEDED", "FAILED").contains(event.status())
                || !Set.of("ARTIFACT_DELETED", "ARTIFACT_DELETE_FAILED")
                .contains(event.resultCode())) {
            throw new IllegalArgumentException("Unsafe artifact retention event");
        }
        if (processed.existsById(event.eventId())) {
            return;
        }
        val execution = executions.findById(event.executionId())
                .orElseThrow(() -> new IllegalArgumentException("Unknown execution"));
        if (!execution.getEntity().getId().equals(event.entityId())
                || !execution.getOwner().getId().equals(event.actorUserId())) {
            throw new IllegalArgumentException("Artifact retention binding mismatch");
        }
        val artifact = artifacts.findById(event.artifactId())
                .orElseThrow(() -> new IllegalArgumentException("Unknown artifact"));
        if (!artifact.getResult().getExecution().getId().equals(event.executionId())
                || !artifact.getBucketName().equals(event.bucket())
                || !artifact.getObjectKey().equals(event.objectKey())) {
            throw new IllegalArgumentException("Artifact retention target mismatch");
        }
        if ("SUCCEEDED".equals(event.status())) {
            artifacts.markDeleted(event.artifactId());
        } else {
            artifacts.markDeletionFailed(event.artifactId());
        }
        processed.save(ProcessedExecutionEventModel.builder()
                .eventId(event.eventId()).eventType("ARTIFACT_RETENTION")
                .execution(execution).processedAt(Instant.now(clock)).build());
    }

    private void requireEnvelope(String version, UUID eventId, String correlationId,
                                 UUID executionId, UUID entityId) {
        if (!"1.0".equals(version) || eventId == null || executionId == null || entityId == null
                || correlationId == null || correlationId.isBlank()
                || correlationId.length() > 100) {
            throw new IllegalArgumentException("Invalid execution event envelope");
        }
    }

    private String json(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (Exception exception) {
            throw new IllegalArgumentException("Invalid event details", exception);
        }
    }

    private boolean invalidAuditText(String value, int maximumLength) {
        return value == null || value.isBlank() || value.length() > maximumLength
                || value.chars().anyMatch(character -> Character.isISOControl(character));
    }

    private void afterCommit(
            UUID executionId, String userSubject, UUID eventId, String type, Object event) {
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                hub.publish(executionId, userSubject, eventId, type, event);
            }
        });
    }

}
