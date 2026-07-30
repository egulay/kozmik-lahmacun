package io.gulay.execution.data.service;

import lombok.val;

import tools.jackson.databind.ObjectMapper;
import io.gulay.api.ResourceNotFoundException;
import io.gulay.audit.data.model.AuditOutcome;
import io.gulay.audit.data.service.AuditEventService;
import io.gulay.execution.data.model.ExecutionRequestModel;
import io.gulay.execution.data.model.ExecutionStatus;
import io.gulay.execution.data.model.ExecutionStatusHistoryModel;
import io.gulay.execution.data.repository.ExecutionRequestRepository;
import io.gulay.execution.data.repository.ExecutionStatusHistoryRepository;
import io.gulay.execution.messaging.ExecutionMessagingContracts;
import io.gulay.execution.messaging.KafkaMessageSigner;

import java.time.Clock;
import java.time.Instant;
import java.util.UUID;
import java.util.Set;

import io.gulay.security.PlatformRole;
import io.gulay.user.data.repository.AppUserReferenceRepository;
import lombok.RequiredArgsConstructor;
import org.slf4j.MDC;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
public class ExecutionLifecycleService {
    private final ExecutionRequestRepository executions;
    private final ExecutionStatusHistoryRepository history;
    private final AuditEventService audit;
    private final KafkaTemplate<String, String> kafka;
    private final ObjectMapper mapper;
    private final KafkaMessageSigner signer;
    private final Clock clock;
    private final AppUserReferenceRepository users;

    @Value("${kozmik.kafka.control-topic:execution.control.v1}")
    private String controlTopic;

    @Transactional
    public void cancel(
            UUID executionId, String keycloakUserId, Set<PlatformRole> roles) {
        val candidate = roles.contains(PlatformRole.ADMIN)
                ? executions.findById(executionId)
                : executions.findByIdAndOwnerKeycloakUserId(executionId, keycloakUserId);
        val execution = candidate
                .orElseThrow(() -> new ResourceNotFoundException("Execution not found"));
        val actor = users.findByKeycloakUserId(keycloakUserId)
                .orElseThrow(() -> new ResourceNotFoundException("User reference not found"));
        val now = Instant.now(clock);
        val changed = execution.requestCancellation(now);
        if (changed) {
            val eventId = UUID.randomUUID();
            history.save(ExecutionStatusHistoryModel.builder()
                    .id(UUID.randomUUID()).eventId(eventId).execution(execution)
                    .stage("CANCELLATION_REQUESTED").status(execution.getStatus())
                    .progress(0).messageCode("EXECUTION_CANCELLATION_REQUESTED")
                    .messageParameters("{}").occurredAt(now).build());
            publish(execution, eventId, now);
            audit.record("EXECUTION_CANCELLATION_REQUESTED", actor,
                    "EXECUTION", executionId.toString(), correlationId(),
                    AuditOutcome.SUCCEEDED, "CANCELLATION_COMMAND_PUBLISHED");
        }
    }

    @Scheduled(fixedDelayString = "${kozmik.execution.timeout-scan-ms:30000}")
    @Transactional
    public void markOverdue() {
        val now = Instant.now(clock);
        for (val execution : executions.findOverdue(now)) {
            if (!execution.applyStatus(ExecutionStatus.TIMED_OUT, now)) continue;
            val eventId = UUID.randomUUID();
            history.save(ExecutionStatusHistoryModel.builder()
                    .id(UUID.randomUUID()).eventId(eventId).execution(execution)
                    .stage("TIMED_OUT").status(ExecutionStatus.TIMED_OUT).progress(100)
                    .messageCode("EXECUTION_TIMEOUT").messageParameters("{}")
                    .occurredAt(now).build());
            publish(execution, eventId, now);
            audit.record("EXECUTION_TIMED_OUT", execution.getOwner(), "EXECUTION",
                    execution.getId().toString(), execution.getCorrelationId(),
                    AuditOutcome.SUCCEEDED, "CONTROL_PLANE_TIMEOUT");
        }
    }

    private void publish(ExecutionRequestModel execution, UUID eventId, Instant now) {
        try {
            val command = new ExecutionMessagingContracts.ExecutionControlCommand(
                    "1.0", eventId, execution.getCorrelationId(), execution.getId(),
                    execution.getEntity().getId(), execution.getOwner().getId(), now, "CANCEL");
            kafka.send(controlTopic, execution.getId().toString(),
                    signer.wrap(mapper.writeValueAsString(command)));
        } catch (Exception exception) {
            throw new IllegalStateException("Unable to publish lifecycle command", exception);
        }
    }

    private String correlationId() {
        val value = MDC.get("correlationId");
        return value == null ? UUID.randomUUID().toString() : value;
    }
}
