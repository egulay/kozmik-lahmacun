package io.gulay.execution.messaging;

import lombok.val;

import java.io.IOException;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;

@Component
public class ExecutionEventHub {
    private final Map<UUID, CopyOnWriteArrayList<SseEmitter>> emitters = new ConcurrentHashMap<>();
    private final int maxSubscribers;

    public ExecutionEventHub(
            @Value("${kozmik.sse.max-subscribers-per-stream:10000}") int maxSubscribers) {
        this.maxSubscribers = maxSubscribers;
    }

    public SseEmitter subscribe(UUID executionId) {
        val values = emitters.computeIfAbsent(
                executionId, ignored -> new CopyOnWriteArrayList<>());
        if (values.size() >= maxSubscribers) {
            throw new ResponseStatusException(
                    HttpStatus.TOO_MANY_REQUESTS, "SSE subscriber limit reached");
        }
        val emitter = new SseEmitter(300_000L);
        values.add(emitter);
        emitter.onCompletion(() -> remove(executionId, emitter));
        emitter.onTimeout(() -> remove(executionId, emitter));
        emitter.onError(error -> remove(executionId, emitter));
        return emitter;
    }

    public void publish(UUID executionId, UUID eventId, String type, Object data) {
        for (val emitter : emitters.getOrDefault(executionId, new CopyOnWriteArrayList<>())) {
            try {
                emitter.send(SseEmitter.event().id(eventId.toString()).name(type).data(data));
            } catch (IOException exception) {
                emitter.complete();
                remove(executionId, emitter);
            }
        }
    }

    private void remove(UUID executionId, SseEmitter emitter) {
        val values = emitters.get(executionId);
        if (values != null) {
            values.remove(emitter);
            if (values.isEmpty()) {
                emitters.remove(executionId, values);
            }
        }
    }
}
