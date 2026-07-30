package io.gulay.chat.data.service;

import lombok.val;

import io.gulay.chat.client.PythonChatClient;
import io.gulay.chat.client.PythonChatContracts;
import io.gulay.entity.data.service.EntityManagementService;
import io.gulay.entity.dto.EntityDtos;
import io.gulay.execution.data.service.ReportPlanningService;
import io.gulay.execution.dto.ExecutionDtos;
import io.gulay.execution.ReportPlanningException;
import io.gulay.security.PlatformRole;

import java.text.Normalizer;
import java.util.ArrayDeque;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.Executor;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;

@Component
@Slf4j
public class ChatStreamCoordinator {
    private static final int MAX_CLASSIFICATION_HISTORY_MESSAGES = 10;
    private static final int MAX_CLASSIFICATION_CONTEXT_CHARACTERS = 8_000;

    private final PythonChatClient client;
    private final ChatService chatService;
    private final ChatStreamHub hub;
    private final Executor executor;
    private final EntityManagementService entityService;
    private final ReportPlanningService planningService;

    public ChatStreamCoordinator(
            PythonChatClient client,
            ChatService chatService,
            ChatStreamHub hub,
            EntityManagementService entityService,
            ReportPlanningService planningService,
            @Qualifier("chatExecutor") Executor executor) {
        this.client = client;
        this.chatService = chatService;
        this.hub = hub;
        this.entityService = entityService;
        this.planningService = planningService;
        this.executor = executor;
    }

    public void start(PythonChatContracts.StreamRequest request, String keycloakUserId,
                      Set<PlatformRole> roles, String userRequest) {
        executor.execute(() -> classifyAndRun(
                request, keycloakUserId, roles, userRequest));
    }

    private void classifyAndRun(PythonChatContracts.StreamRequest request,
                                String keycloakUserId, Set<PlatformRole> roles,
                                String userRequest) {
        try {
            val visibleEntities = entityService.list(
                    keycloakUserId, roles, request.language()).entities();
            val metadata = visibleEntities.stream()
                    .filter(EntityDtos.EntitySummary::schemaRegistered)
                    .map(entity -> metadata(
                            entity, keycloakUserId, roles, request.language()))
                    .toList();
            val history = classificationHistory(request.history(), userRequest);
            val classification = client.classify(
                    new PythonChatContracts.ClassificationRequest(
                            "1.0", request.requestId(), request.correlationId(),
                            request.actorUserId(), request.language(),
                            request.capabilities(), userRequest, history, metadata));
            if ("REPORT".equals(classification.intent())
                    || "ML".equals(classification.intent())) {
                acceptExecutionRequest(request, keycloakUserId, roles, userRequest,
                        visibleEntities, classification);
                return;
            }
            if (!"CONVERSATIONAL".equals(classification.intent())) {
                throw new IllegalStateException("Unsupported intent classification");
            }
            run(request);
        } catch (Exception exception) {
            fail(request, "CHAT_CLASSIFICATION_OR_PLANNING_FAILED", exception);
        }
    }

    private List<PythonChatContracts.HistoryMessage> classificationHistory(
            List<PythonChatContracts.HistoryMessage> requestHistory, String userRequest) {
        val selected = new ArrayDeque<PythonChatContracts.HistoryMessage>();
        var characters = userRequest.length();
        // The last history item is the current user request and is supplied separately.
        for (var index = requestHistory.size() - 2;
             index >= 0 && selected.size() < MAX_CLASSIFICATION_HISTORY_MESSAGES;
             index--) {
            val message = requestHistory.get(index);
            if (characters + message.content().length()
                    > MAX_CLASSIFICATION_CONTEXT_CHARACTERS) {
                break;
            }
            selected.addFirst(message);
            characters += message.content().length();
        }
        return List.copyOf(selected);
    }

    private PythonChatContracts.EntityMetadata metadata(
            EntityDtos.EntitySummary entity, String keycloakUserId,
            Set<PlatformRole> roles, String language) {
        val schema = entityService.currentSchema(
                entity.id(), keycloakUserId, roles, language);
        return new PythonChatContracts.EntityMetadata(
                entity.id(), entity.name(), entity.description(),
                schema.columns().stream()
                        .map(EntityDtos.ColumnDefinition::columnName).toList());
    }

    private void acceptExecutionRequest(
            PythonChatContracts.StreamRequest request, String keycloakUserId,
            Set<PlatformRole> roles, String userRequest,
            List<EntityDtos.EntitySummary> entities,
            PythonChatContracts.ClassificationResponse classification) {
        val entity = resolveEntity(
                userRequest, entities, classification.selectedEntityId());
        if (entity == null) {
            complete(request, classification,
                    request.language().startsWith("tr")
                            ? "Lütfen rapor veya model için veri varlığını belirtin. Kullanılabilir varlıklar: "
                            + entityNames(entities)
                            : "Please specify the data entity for this report or model. Available entities: "
                            + entityNames(entities));
            return;
        }
        val effectiveRequest = effectiveExecutionRequest(request, userRequest, entity);
        val planningRequest = new ExecutionDtos.CreateReportPlanRequest(
                entity.id(), effectiveRequest, request.language());
        val idempotencyKey = "chat-" + request.assistantMessageId();
        final ExecutionDtos.ReportPlanResponse pending;
        try {
            pending = planningService.createPending(
                    planningRequest, idempotencyKey, keycloakUserId, roles,
                    request.correlationId(), classification.intent());
        } catch (Exception exception) {
            fail(request, "EXECUTION_REQUEST_CREATION_FAILED", exception);
            return;
        }
        val acknowledgement = request.language().startsWith("tr")
                ? "%s için %s isteğiniz alındı ve arka planda hazırlanıyor. Sohbete devam edebilirsiniz. Çalıştırma kimliği: %s"
                .formatted(entity.name(),
                        "ML".equals(classification.intent()) ? "ML" : "rapor",
                        pending.id())
                : "Your %s request for %s was received and is being prepared in the background. You can continue chatting. Execution ID: %s"
                .formatted("ML".equals(classification.intent()) ? "ML" : "report",
                        entity.name(), pending.id());
        complete(request, classification, acknowledgement);
        executor.execute(() -> createExecutionInBackground(
                request, keycloakUserId, roles, pending.id()));
    }

    private void createExecutionInBackground(
            PythonChatContracts.StreamRequest request, String keycloakUserId,
            Set<PlatformRole> roles, UUID executionId) {
        try {
            val result = planningService.completePending(
                    executionId, keycloakUserId, roles);
            log.info(
                    "Background chat execution created assistantMessageId={} executionId={} executionType={}",
                    request.assistantMessageId(), result.id(), result.executionType());
        } catch (ReportPlanningException exception) {
            planningService.failPending(executionId, "EXECUTION_PLANNING_REJECTED");
            log.warn(
                    "Background chat execution planning rejected assistantMessageId={} reason={}",
                    request.assistantMessageId(), exception.getMessage());
        } catch (Exception exception) {
            planningService.failPending(executionId, "EXECUTION_PLANNING_FAILED");
            log.error(
                    "Background chat execution creation failed assistantMessageId={} errorType={}",
                    request.assistantMessageId(), exception.getClass().getSimpleName(), exception);
        }
    }

    private EntityDtos.EntitySummary resolveEntity(
            String request, List<EntityDtos.EntitySummary> entities,
            UUID selectedEntityId) {
        if (selectedEntityId != null) {
            val selected = entities.stream()
                    .filter(entity -> entity.id().equals(selectedEntityId))
                    .findFirst();
            if (selected.isPresent()) {
                return selected.get();
            }
        }
        val normalizedRequest = normalize(request);
        val matches = entities.stream()
                .filter(entity -> {
                    val normalizedName = normalize(entity.name());
                    val canonicalName = normalize(entity.canonicalName());
                    return normalizedRequest.contains(normalizedName)
                            || (normalizedRequest.length() >= 3
                            && normalizedName.contains(normalizedRequest))
                            || normalizedRequest.contains(canonicalName)
                            || (normalizedRequest.length() >= 3
                            && canonicalName.contains(normalizedRequest));
                })
                .toList();
        if (matches.size() == 1) {
            return matches.get(0);
        }
        return entities.size() == 1 ? entities.get(0) : null;
    }

    private String effectiveExecutionRequest(
            PythonChatContracts.StreamRequest request, String userRequest,
            EntityDtos.EntitySummary entity) {
        val normalizedRequest = normalize(userRequest);
        val normalizedName = normalize(entity.name());
        val canonicalName = normalize(entity.canonicalName());
        val entityOnly = normalizedRequest.equals(normalizedName)
                || (normalizedRequest.length() >= 3
                && normalizedName.contains(normalizedRequest))
                || normalizedRequest.equals(canonicalName)
                || (normalizedRequest.length() >= 3
                && canonicalName.contains(normalizedRequest));
        if (!entityOnly) {
            return userRequest;
        }
        val history = request.history();
        var skippedCurrent = false;
        for (var index = history.size() - 1; index >= 0; index--) {
            val message = history.get(index);
            if (!"user".equalsIgnoreCase(message.role())) {
                continue;
            }
            if (!skippedCurrent) {
                skippedCurrent = true;
                continue;
            }
            if (!message.content().isBlank()) {
                return message.content();
            }
        }
        return userRequest;
    }

    private String entityNames(List<EntityDtos.EntitySummary> entities) {
        return entities.stream().map(EntityDtos.EntitySummary::name)
                .sorted().reduce((left, right) -> left + ", " + right).orElse("none");
    }

    private String normalize(String value) {
        return Normalizer.normalize(value, Normalizer.Form.NFKD)
                .replaceAll("\\p{M}", "").toLowerCase(Locale.ROOT);
    }

    private void complete(
            PythonChatContracts.StreamRequest request,
            PythonChatContracts.ClassificationResponse classification,
            String content) {
        chatService.complete(request.assistantMessageId(), content,
                classification.provider(), classification.model());
        val event = new PythonChatContracts.StreamEvent(
                "1.0", UUID.randomUUID(), request.correlationId(),
                request.assistantMessageId(), "message-completed", null, content,
                classification.provider(), classification.model(), null);
        hub.publish(request.assistantMessageId(), eventId(request, 1),
                "message-completed", event, true);
    }

    private void run(PythonChatContracts.StreamRequest request) {
        val index = new AtomicInteger();
        val terminal = new AtomicBoolean();
        val content = new StringBuilder();
        try {
            client.stream(request, event -> {
                val eventIndex = index.incrementAndGet();
                switch (event.type()) {
                    case "message-started" -> {
                        chatService.markStreaming(
                                request.assistantMessageId(), event.provider(), event.model());
                        hub.publish(request.assistantMessageId(), eventId(request, eventIndex),
                                "message-started", event, false);
                    }
                    case "message-delta" -> {
                        if (event.delta() != null) {
                            content.append(event.delta());
                        }
                        hub.publish(request.assistantMessageId(), eventId(request, eventIndex),
                                "message-delta", event, false);
                    }
                    case "message-completed" -> {
                        val finalContent = event.content() == null ? content.toString() : event.content();
                        chatService.complete(request.assistantMessageId(), finalContent,
                                event.provider(), event.model());
                        hub.publish(request.assistantMessageId(), eventId(request, eventIndex),
                                "message-completed", event, true);
                        terminal.set(true);
                    }
                    case "message-failed" -> {
                        chatService.fail(request.assistantMessageId(),
                                safeCode(event.errorCode()));
                        hub.publish(request.assistantMessageId(), eventId(request, eventIndex),
                                "message-failed", event, true);
                        terminal.set(true);
                    }
                    default -> throw new IllegalStateException("Unsupported chat stream event");
                }
            });
            if (!terminal.get()) {
                throw new IllegalStateException("Python stream ended without terminal event");
            }
        } catch (Exception exception) {
            fail(request, "CHAT_PROVIDER_UNAVAILABLE", exception);
        }
    }

    private void fail(PythonChatContracts.StreamRequest request, String code,
                      Exception exception) {
        log.error("Chat orchestration failed assistantMessageId={} requestId={} code={} errorType={}",
                request.assistantMessageId(), request.requestId(), code,
                exception.getClass().getSimpleName(), exception);
        chatService.fail(request.assistantMessageId(), code);
        val failed = new PythonChatContracts.StreamEvent(
                "1.0", UUID.randomUUID(), request.correlationId(),
                request.assistantMessageId(), "message-failed", null, null,
                null, null, code);
        hub.publish(request.assistantMessageId(), eventId(request, 999_999),
                "message-failed", failed, true);
    }

    private String eventId(PythonChatContracts.StreamRequest request, int index) {
        return request.assistantMessageId() + ":" + String.format("%06d", index);
    }

    private String safeCode(String code) {
        return code == null || code.isBlank() ? "CHAT_PROVIDER_FAILED" : code;
    }
}
