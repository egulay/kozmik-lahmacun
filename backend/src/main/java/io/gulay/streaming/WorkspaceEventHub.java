package io.gulay.streaming;

import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/** User-scoped sidebar/workspace notifications carried by one durable UI stream. */
@Component
public class WorkspaceEventHub {
    private final SseEventBroker<String> userBroker;
    private final SseEventBroker<String> administratorBroker;

    public WorkspaceEventHub(
            @Value("${kozmik.sse.max-subscribers-per-stream:10000}") int maxSubscribers) {
        userBroker = new SseEventBroker<>(maxSubscribers, 300_000L);
        administratorBroker = new SseEventBroker<>(maxSubscribers, 300_000L);
    }

    public SseEmitter subscribe(String userSubject, boolean administrator) {
        return administrator
                ? administratorBroker.subscribe(userSubject)
                : userBroker.subscribe(userSubject);
    }

    public void publishOwned(
            String userSubject, UUID eventId, String eventName, Object data) {
        userBroker.publish(userSubject, eventId.toString(), eventName, data);
        administratorBroker.publish(userSubject, eventId.toString(), eventName, data);
    }

    public void publishExecution(
            String userSubject, UUID eventId, String eventName, Object data) {
        userBroker.publish(userSubject, eventId.toString(), eventName, data);
        administratorBroker.publishAll(eventId.toString(), eventName, data);
    }

    public void publishAll(String eventName, Object data) {
        var eventId = UUID.randomUUID().toString();
        userBroker.publishAll(eventId, eventName, data);
        administratorBroker.publishAll(eventId, eventName, data);
    }
}
