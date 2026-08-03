package io.gulay.executor.client;

import lombok.Getter;
import lombok.val;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/** Shared authenticated transport for every Java-to-executor operation. */
@Component
public class PythonExecutorTransport {
    private final HttpClient client;
    private final String baseUrl;
    @Getter
    private final String internalApiKey;

    public PythonExecutorTransport(
            @Value("${kozmik.python.base-url:http://localhost:8000}") String baseUrl,
            @Value("${kozmik.security.internal-api-key:}") String internalApiKey) {
        this.baseUrl = baseUrl.replaceFirst("/+$", "");
        this.internalApiKey = internalApiKey;
        this.client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofSeconds(5))
                .build();
    }

    public HttpResponse<String> get(String path, Duration timeout) {
        return send(request(path, timeout)
                .header("Accept", "application/json").GET().build(),
                HttpResponse.BodyHandlers.ofString());
    }

    public HttpResponse<String> postJson(
            String path, String body, String correlationId, Duration timeout) {
        return send(request(path, timeout)
                .header("Content-Type", "application/json")
                .header("Accept", "application/json")
                .header("X-Correlation-ID", safeCorrelationId(correlationId))
                .POST(HttpRequest.BodyPublishers.ofString(body)).build(),
                HttpResponse.BodyHandlers.ofString());
    }

    public HttpResponse<java.util.stream.Stream<String>> postJsonLines(
            String path, String body, String correlationId, Duration timeout) {
        return send(request(path, timeout)
                .header("Content-Type", "application/json")
                .header("Accept", "application/x-ndjson")
                .header("X-Correlation-ID", safeCorrelationId(correlationId))
                .POST(HttpRequest.BodyPublishers.ofString(body)).build(),
                HttpResponse.BodyHandlers.ofLines());
    }

    private HttpRequest.Builder request(String path, Duration timeout) {
        return HttpRequest.newBuilder()
                .uri(URI.create(baseUrl + path))
                .header("X-Internal-API-Key", internalApiKey)
                .timeout(timeout);
    }

    private <T> HttpResponse<T> send(
            HttpRequest request, HttpResponse.BodyHandler<T> handler) {
        try {
            return client.send(request, handler);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new PythonExecutorTransportException("Executor request interrupted", exception);
        } catch (Exception exception) {
            throw new PythonExecutorTransportException("Executor request failed", exception);
        }
    }

    private String safeCorrelationId(String value) {
        return value == null ? "" : value;
    }

    public static final class PythonExecutorTransportException extends RuntimeException {
        public PythonExecutorTransportException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
