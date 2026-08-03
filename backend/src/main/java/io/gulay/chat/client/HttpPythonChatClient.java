package io.gulay.chat.client;

import lombok.val;

import tools.jackson.databind.ObjectMapper;

import java.time.Duration;
import java.util.function.Consumer;

import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import io.gulay.executor.client.PythonExecutorTransport;

@Component
@RequiredArgsConstructor
public class HttpPythonChatClient implements PythonChatClient {
    private final ObjectMapper objectMapper;
    private final PythonExecutorTransport transport;
    @Value("${kozmik.python.chat-stream-timeout-seconds:240}")
    private long chatStreamTimeoutSeconds;
    @Value("${kozmik.python.classification-timeout-seconds:240}")
    private long classificationTimeoutSeconds;

    @Override
    public void stream(PythonChatContracts.StreamRequest request,
                       Consumer<PythonChatContracts.StreamEvent> eventConsumer) {
        try {
            val body = objectMapper.writeValueAsString(request);
            val response = transport.postJsonLines("/internal/v1/chat/stream", body,
                    request.correlationId(), Duration.ofSeconds(chatStreamTimeoutSeconds));
            if (response.statusCode() != 200) {
                throw new IllegalStateException("Python chat endpoint unavailable");
            }
            try (val lines = response.body()) {
                lines.filter(line -> !line.isBlank())
                        .map(this::parse)
                        .forEach(eventConsumer);
            }
        } catch (Exception exception) {
            throw new IllegalStateException("Python chat stream failed", exception);
        }
    }

    @Override
    public PythonChatContracts.ClassificationResponse classify(
            PythonChatContracts.ClassificationRequest request) {
        try {
            val body = objectMapper.writeValueAsString(request);
            val response = transport.postJson("/internal/v1/chat/classify", body,
                    request.correlationId(), Duration.ofSeconds(classificationTimeoutSeconds));
            if (response.statusCode() != 200) {
                throw new IllegalStateException("Python classification endpoint unavailable");
            }
            return objectMapper.readValue(
                    response.body(), PythonChatContracts.ClassificationResponse.class);
        } catch (Exception exception) {
            throw new IllegalStateException("Python classification failed", exception);
        }
    }

    private PythonChatContracts.StreamEvent parse(String line) {
        try {
            return objectMapper.readValue(line, PythonChatContracts.StreamEvent.class);
        } catch (Exception exception) {
            throw new IllegalStateException("Invalid Python chat event", exception);
        }
    }
}
