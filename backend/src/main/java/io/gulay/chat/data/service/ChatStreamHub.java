package io.gulay.chat.data.service;

import lombok.val;

import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

import io.gulay.streaming.SseEventBroker;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@Component
public class ChatStreamHub {
    private final Map<UUID, List<Event>> events = new ConcurrentHashMap<>();
    private final SseEventBroker<UUID> broker;

    public ChatStreamHub(
            @Value("${kozmik.sse.max-subscribers-per-stream:10000}") int maxSubscribers) {
        this.broker = new SseEventBroker<>(maxSubscribers, 300_000L);
    }

    public SseEmitter subscribe(UUID messageId, String lastEventId) {
        val emitter = broker.subscribe(messageId);
        for (val event : events.getOrDefault(messageId, List.of())) {
            if (lastEventId == null || event.id().compareTo(lastEventId) > 0) {
                broker.send(messageId, emitter, event.id(), event.name(),
                        event.data(), event.terminal());
            }
        }
        return emitter;
    }

    public void publish(UUID messageId, String id, String name, Object data, boolean terminal) {
        val event = new Event(id, name, data, terminal);
        events.computeIfAbsent(messageId, ignored -> new java.util.concurrent.CopyOnWriteArrayList<>())
                .add(event);
        broker.publish(messageId, id, name, data, terminal);
        if (terminal) {
            events.remove(messageId);
        }
    }

    public SseEmitter terminal(UUID messageId, String id, String name, Object data) {
        val emitter = broker.subscribe(messageId);
        broker.send(messageId, emitter, id, name, data, true);
        return emitter;
    }

    private record Event(String id, String name, Object data, boolean terminal) {
    }
}
