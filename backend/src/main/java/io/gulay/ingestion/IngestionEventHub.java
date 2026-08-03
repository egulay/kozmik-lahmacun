package io.gulay.ingestion;

import lombok.val;

import java.io.IOException;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@Component
public class IngestionEventHub {
    private final Map<UUID, CopyOnWriteArrayList<SseEmitter>> subscribers =
            new ConcurrentHashMap<>();
    private final CopyOnWriteArrayList<SseEmitter> globalSubscribers =
            new CopyOnWriteArrayList<>();
    private final int maxSubscribers;

    public IngestionEventHub(
            @Value("${kozmik.sse.max-subscribers-per-stream:10000}") int maxSubscribers) {
        this.maxSubscribers = maxSubscribers;
    }

    public SseEmitter subscribeAll() {
        if (globalSubscribers.size() >= maxSubscribers) {
            throw new ResponseStatusException(
                    HttpStatus.TOO_MANY_REQUESTS, "SSE subscriber limit reached");
        }
        val emitter = new SseEmitter(300_000L);
        globalSubscribers.add(emitter);
        emitter.onCompletion(() -> globalSubscribers.remove(emitter));
        emitter.onTimeout(() -> globalSubscribers.remove(emitter));
        emitter.onError(error -> globalSubscribers.remove(emitter));
        return emitter;
    }

    public SseEmitter subscribe(UUID entityId) {
        val entitySubscribers = subscribers.computeIfAbsent(
                entityId, ignored -> new CopyOnWriteArrayList<>());
        if (entitySubscribers.size() >= maxSubscribers) {
            throw new ResponseStatusException(
                    HttpStatus.TOO_MANY_REQUESTS, "SSE subscriber limit reached");
        }
        val emitter = new SseEmitter(300_000L);
        entitySubscribers.add(emitter);
        emitter.onCompletion(() -> remove(entityId, emitter));
        emitter.onTimeout(() -> remove(entityId, emitter));
        emitter.onError(error -> remove(entityId, emitter));
        return emitter;
    }

    public void publish(IngestionUiEvent event) {
        publishGlobal(event);
        for (val emitter : subscribers.getOrDefault(
                event.entityId(), new CopyOnWriteArrayList<>())) {
            try {
                emitter.send(SseEmitter.event().id(event.eventId().toString())
                        .name(event.eventType()).data(event));
            } catch (IOException exception) {
                emitter.complete();
                remove(event.entityId(), emitter);
            }
        }
    }

    private void publishGlobal(IngestionUiEvent event) {
        val notification = new GlobalIngestionNotification(
                "1.0", event.eventId(), event.entityId(),
                "entity-ingestion-changed", event.ingestionKind(),
                event.stage(), event.status(), event.occurredAt());
        for (val emitter : globalSubscribers) {
            try {
                emitter.send(SseEmitter.event().id(event.eventId().toString())
                        .name(notification.eventType()).data(notification));
            } catch (IOException exception) {
                emitter.complete();
                globalSubscribers.remove(emitter);
            }
        }
    }

    private void remove(UUID entityId, SseEmitter emitter) {
        val values = subscribers.get(entityId);
        if (values != null) {
            values.remove(emitter);
            if (values.isEmpty()) subscribers.remove(entityId, values);
        }
    }

    public record IngestionUiEvent(
            String schemaVersion, UUID eventId, UUID entityId, String eventType,
            String ingestionKind, String stage, String status, String messageCode,
            Long batchRowCount, Long cumulativeRowCount, Instant occurredAt) {
    }

    public record GlobalIngestionNotification(
            String schemaVersion, UUID eventId, UUID entityId, String eventType,
            String ingestionKind, String stage, String status, Instant occurredAt) {
    }
}
