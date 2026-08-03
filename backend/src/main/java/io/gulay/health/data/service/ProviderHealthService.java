package io.gulay.health.data.service;

import lombok.val;

import java.util.Map;
import java.time.Duration;

import org.springframework.stereotype.Service;
import tools.jackson.databind.ObjectMapper;
import io.gulay.executor.client.PythonExecutorTransport;

@Service
public class ProviderHealthService {
    private final PythonExecutorTransport transport;
    private final ObjectMapper objectMapper;

    public ProviderHealthService(
            PythonExecutorTransport transport, ObjectMapper objectMapper) {
        this.transport = transport;
        this.objectMapper = objectMapper;
    }

    public Snapshot check() {
        if (transport.getInternalApiKey().isBlank()) {
            return new Snapshot("UNKNOWN", "UNKNOWN", null, null, null);
        }
        try {
            val httpResponse = transport.get("/internal/v1/health", Duration.ofSeconds(5));
            if (httpResponse.statusCode() != 200) {
                return new Snapshot("UNAVAILABLE", "UNKNOWN", null, null,
                        "EXECUTOR_UNAVAILABLE");
            }
            val response = objectMapper.readValue(httpResponse.body(), Map.class);
            if (response == null) {
                return new Snapshot("UNAVAILABLE", "UNKNOWN", null, null,
                        "EXECUTOR_UNAVAILABLE");
            }
            return new Snapshot(
                    safe(response.get("status")),
                    safe(response.get("providerStatus")),
                    nullable(response.get("provider")),
                    nullable(response.get("model")),
                    nullable(response.get("errorCode")));
        } catch (RuntimeException unavailable) {
            return new Snapshot("UNAVAILABLE", "UNKNOWN", null, null,
                    "EXECUTOR_UNAVAILABLE");
        }
    }

    private String safe(Object value) {
        return value == null ? "UNKNOWN" : value.toString();
    }

    private String nullable(Object value) {
        return value == null ? null : value.toString();
    }

    public record Snapshot(
            String pythonStatus,
            String providerStatus,
            String provider,
            String model,
            String errorCode) {
    }
}
