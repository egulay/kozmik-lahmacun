package io.gulay.execution.messaging;

import java.util.UUID;

import io.gulay.streaming.SseEventBroker;
import io.gulay.streaming.WorkspaceEventHub;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@Component
public class ExecutionEventHub {
    private final SseEventBroker<UUID> broker;
    private final WorkspaceEventHub workspace;

    public ExecutionEventHub(
            WorkspaceEventHub workspace,
            @Value("${kozmik.sse.max-subscribers-per-stream:10000}") int maxSubscribers) {
        this.workspace = workspace;
        this.broker = new SseEventBroker<>(maxSubscribers, 300_000L);
    }

    public SseEmitter subscribe(UUID executionId) {
        return broker.subscribe(executionId);
    }

    public SseEmitter subscribeAll(String userSubject, boolean administrator) {
        return workspace.subscribe(userSubject, administrator);
    }

    public void publish(
            UUID executionId, String userSubject, UUID eventId, String type, Object data) {
        broker.publish(executionId, eventId.toString(), type, data);
        workspace.publishExecution(userSubject, eventId, type, data);
    }
}
