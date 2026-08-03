package io.gulay.ingestion;

import lombok.val;

import java.time.Instant;
import java.util.UUID;

import io.gulay.streaming.SseEventBroker;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@Component
public class IngestionEventHub {
    private static final String GLOBAL_STREAM = "global";
    private final SseEventBroker<UUID> entityBroker;
    private final SseEventBroker<String> globalBroker;

    public IngestionEventHub(
            @Value("${kozmik.sse.max-subscribers-per-stream:10000}") int maxSubscribers) {
        this.entityBroker = new SseEventBroker<>(maxSubscribers, 300_000L);
        this.globalBroker = new SseEventBroker<>(maxSubscribers, 300_000L);
    }

    public SseEmitter subscribeAll() {
        return globalBroker.subscribe(GLOBAL_STREAM);
    }

    public SseEmitter subscribe(UUID entityId) {
        return entityBroker.subscribe(entityId);
    }

    public void publish(IngestionUiEvent event) {
        publishGlobal(event);
        entityBroker.publish(event.entityId(), event.eventId().toString(),
                event.eventType(), event);
    }

    private void publishGlobal(IngestionUiEvent event) {
        val notification = new GlobalIngestionNotification(
                "1.0", event.eventId(), event.entityId(),
                "entity-ingestion-changed", event.ingestionKind(),
                event.stage(), event.status(), event.occurredAt());
        globalBroker.publish(GLOBAL_STREAM, event.eventId().toString(),
                notification.eventType(), notification);
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
