package io.gulay.execution.messaging;

import java.util.UUID;

import io.gulay.streaming.SseEventBroker;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@Component
public class ExecutionEventHub {
    private static final String ADMIN_STREAM = "administrators";
    private final SseEventBroker<UUID> broker;
    private final SseEventBroker<String> userBroker;
    private final SseEventBroker<String> adminBroker;

    public ExecutionEventHub(
            @Value("${kozmik.sse.max-subscribers-per-stream:10000}") int maxSubscribers) {
        this.broker = new SseEventBroker<>(maxSubscribers, 300_000L);
        this.userBroker = new SseEventBroker<>(maxSubscribers, 300_000L);
        this.adminBroker = new SseEventBroker<>(maxSubscribers, 300_000L);
    }

    public SseEmitter subscribe(UUID executionId) {
        return broker.subscribe(executionId);
    }

    public SseEmitter subscribeAll(String userSubject, boolean administrator) {
        return administrator
                ? adminBroker.subscribe(ADMIN_STREAM)
                : userBroker.subscribe(userSubject);
    }

    public void publish(
            UUID executionId, String userSubject, UUID eventId, String type, Object data) {
        broker.publish(executionId, eventId.toString(), type, data);
        userBroker.publish(userSubject, eventId.toString(), type, data);
        adminBroker.publish(ADMIN_STREAM, eventId.toString(), type, data);
    }
}
