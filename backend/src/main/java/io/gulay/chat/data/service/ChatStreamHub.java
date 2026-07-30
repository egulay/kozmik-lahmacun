package io.gulay.chat.data.service;

import lombok.val;

import java.io.IOException;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;

@Component
public class ChatStreamHub {
    private static final int MAX_SUBSCRIBERS_PER_MESSAGE = 5;
    private final Map<UUID, List<Event>> events = new ConcurrentHashMap<>();
    private final Map<UUID, List<SseEmitter>> subscribers = new ConcurrentHashMap<>();

    public SseEmitter subscribe(UUID messageId, String lastEventId) {
        val emitter = new SseEmitter(300_000L);
        val values = subscribers.computeIfAbsent(
                messageId, ignored -> new java.util.concurrent.CopyOnWriteArrayList<>());
        if (values.size() >= MAX_SUBSCRIBERS_PER_MESSAGE) {
            throw new ResponseStatusException(
                    HttpStatus.TOO_MANY_REQUESTS, "SSE subscriber limit reached");
        }
        values.add(emitter);
        emitter.onCompletion(() -> remove(messageId, emitter));
        emitter.onTimeout(() -> remove(messageId, emitter));
        for (val event : events.getOrDefault(messageId, List.of())) {
            if (lastEventId == null || event.id().compareTo(lastEventId) > 0) {
                send(emitter, event);
            }
        }
        return emitter;
    }

    public void publish(UUID messageId, String id, String name, Object data, boolean terminal) {
        val event = new Event(id, name, data, terminal);
        events.computeIfAbsent(messageId, ignored -> new java.util.concurrent.CopyOnWriteArrayList<>())
                .add(event);
        for (val emitter : subscribers.getOrDefault(messageId, List.of())) {
            send(emitter, event);
        }
        if (terminal) {
            subscribers.remove(messageId);
            events.remove(messageId);
        }
    }

    private void send(SseEmitter emitter, Event event) {
        try {
            emitter.send(SseEmitter.event().id(event.id()).name(event.name()).data(event.data()));
            if (event.terminal()) {
                emitter.complete();
            }
        } catch (IOException exception) {
            emitter.completeWithError(exception);
        }
    }

    private void remove(UUID messageId, SseEmitter emitter) {
        val current = subscribers.get(messageId);
        if (current != null) {
            current.remove(emitter);
            if (current.isEmpty()) {
                subscribers.remove(messageId, current);
            }
        }
    }

    private record Event(String id, String name, Object data, boolean terminal) {
    }
}
