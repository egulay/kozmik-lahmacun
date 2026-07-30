package io.gulay.chat.client;

import lombok.val;

import tools.jackson.databind.ObjectMapper;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.function.Consumer;

import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
@RequiredArgsConstructor
public class HttpPythonChatClient implements PythonChatClient {
    private final ObjectMapper objectMapper;
    private final HttpClient httpClient = HttpClient.newBuilder()
            .version(HttpClient.Version.HTTP_1_1)
            .connectTimeout(Duration.ofSeconds(5))
            .build();

    @Value("${kozmik.python.base-url:http://localhost:8000}")
    private String baseUrl;
    @Value("${kozmik.security.internal-api-key:}")
    private String internalApiKey;

    @Override
    public void stream(PythonChatContracts.StreamRequest request,
                       Consumer<PythonChatContracts.StreamEvent> eventConsumer) {
        try {
            val body = objectMapper.writeValueAsString(request);
            val httpRequest = HttpRequest.newBuilder()
                    .uri(URI.create(baseUrl + "/internal/v1/chat/stream"))
                    .header("Content-Type", "application/json")
                    .header("Accept", "application/x-ndjson")
                    .header("X-Internal-API-Key", internalApiKey)
                    .header("X-Correlation-ID", request.correlationId())
                    .timeout(Duration.ofMinutes(2))
                    .POST(HttpRequest.BodyPublishers.ofString(body))
                    .build();
            val response = httpClient.send(httpRequest, HttpResponse.BodyHandlers.ofLines());
            if (response.statusCode() != 200) {
                throw new IllegalStateException("Python chat endpoint unavailable");
            }
            try (val lines = response.body()) {
                lines.filter(line -> !line.isBlank())
                        .map(this::parse)
                        .forEach(eventConsumer);
            }
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Python chat stream interrupted", exception);
        } catch (Exception exception) {
            throw new IllegalStateException("Python chat stream failed", exception);
        }
    }

    @Override
    public PythonChatContracts.ClassificationResponse classify(
            PythonChatContracts.ClassificationRequest request) {
        try {
            val body = objectMapper.writeValueAsString(request);
            val httpRequest = HttpRequest.newBuilder()
                    .uri(URI.create(baseUrl + "/internal/v1/chat/classify"))
                    .header("Content-Type", "application/json")
                    .header("Accept", "application/json")
                    .header("X-Internal-API-Key", internalApiKey)
                    .header("X-Correlation-ID", request.correlationId())
                    .timeout(Duration.ofSeconds(30))
                    .POST(HttpRequest.BodyPublishers.ofString(body))
                    .build();
            val response = httpClient.send(
                    httpRequest, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() != 200) {
                throw new IllegalStateException("Python classification endpoint unavailable");
            }
            return objectMapper.readValue(
                    response.body(), PythonChatContracts.ClassificationResponse.class);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Python classification interrupted", exception);
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
