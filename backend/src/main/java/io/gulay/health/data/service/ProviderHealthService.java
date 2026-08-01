package io.gulay.health.data.service;

import lombok.val;

import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class ProviderHealthService {
    private final RestClient restClient;
    private final String internalApiKey;

    public ProviderHealthService(
            RestClient.Builder builder,
            @Value("${kozmik.python.base-url}") String pythonBaseUrl,
            @Value("${kozmik.security.internal-api-key:}") String internalApiKey) {
        this.restClient = builder.baseUrl(pythonBaseUrl).build();
        this.internalApiKey = internalApiKey;
    }

    public Snapshot check() {
        if (internalApiKey.isBlank()) {
            return new Snapshot("UNKNOWN", "UNKNOWN", null, null, null);
        }
        try {
            val response = restClient.get()
                    .uri("/internal/v1/health")
                    .header("X-Internal-API-Key", internalApiKey)
                    .retrieve()
                    .body(Map.class);
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
