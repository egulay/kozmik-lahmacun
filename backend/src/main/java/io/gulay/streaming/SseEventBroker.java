package io.gulay.streaming;

import lombok.val;

import java.io.IOException;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/**
 * Shared in-memory SSE subscriber lifecycle. Domain hubs own authorization,
 * event contracts, replay, and durable reload semantics.
 */
public final class SseEventBroker<K> {
    private final Map<K, CopyOnWriteArrayList<SseEmitter>> subscribers =
            new ConcurrentHashMap<>();
    private final int maxSubscribers;
    private final long timeoutMillis;

    public SseEventBroker(int maxSubscribers, long timeoutMillis) {
        this.maxSubscribers = maxSubscribers;
        this.timeoutMillis = timeoutMillis;
    }

    public SseEmitter subscribe(K key) {
        val values = subscribers.computeIfAbsent(key, ignored -> new CopyOnWriteArrayList<>());
        if (values.size() >= maxSubscribers) {
            throw new ResponseStatusException(
                    HttpStatus.TOO_MANY_REQUESTS, "SSE subscriber limit reached");
        }
        val emitter = new SseEmitter(timeoutMillis);
        values.add(emitter);
        emitter.onCompletion(() -> remove(key, emitter));
        emitter.onTimeout(() -> remove(key, emitter));
        emitter.onError(error -> remove(key, emitter));
        return emitter;
    }

    public void publish(K key, String eventId, String eventName, Object data) {
        publish(key, eventId, eventName, data, false);
    }

    public void publish(
            K key, String eventId, String eventName, Object data, boolean terminal) {
        for (val emitter : subscribers.getOrDefault(key, new CopyOnWriteArrayList<>())) {
            send(key, emitter, eventId, eventName, data, terminal);
        }
        if (terminal) {
            subscribers.remove(key);
        }
    }

    public void send(
            K key, SseEmitter emitter, String eventId, String eventName,
            Object data, boolean terminal) {
        try {
            emitter.send(SseEmitter.event().id(eventId).name(eventName).data(data));
            if (terminal) {
                emitter.complete();
                remove(key, emitter);
            }
        } catch (IOException exception) {
            emitter.completeWithError(exception);
            remove(key, emitter);
        }
    }

    private void remove(K key, SseEmitter emitter) {
        val values = subscribers.get(key);
        if (values == null) {
            return;
        }
        values.remove(emitter);
        if (values.isEmpty()) {
            subscribers.remove(key, values);
        }
    }
}
