package io.gulay.execution.client;

import java.util.List;
import java.util.UUID;

import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
@RequiredArgsConstructor
public class HttpExecutionArtifactDeletionClient implements ExecutionArtifactDeletionClient {

    private final RestClient.Builder restClientBuilder;

    @Value("${kozmik.python.base-url:http://localhost:8000}")
    private String pythonBaseUrl;
    @Value("${kozmik.security.internal-api-key:}")
    private String internalApiKey;

    @Override
    public void delete(
            UUID executionId, String correlationId, List<ArtifactLocation> artifacts) {
        if (artifacts.isEmpty()) {
            return;
        }
        restClientBuilder.baseUrl(pythonBaseUrl).build()
                .post()
                .uri("/internal/v1/artifacts/delete")
                .contentType(MediaType.APPLICATION_JSON)
                .header("X-Internal-API-Key", internalApiKey)
                .header("X-Correlation-ID", correlationId)
                .body(new DeleteRequest("1.0", executionId, artifacts))
                .retrieve()
                .toBodilessEntity();
    }

    private record DeleteRequest(
            String schemaVersion,
            UUID executionId,
            List<ArtifactLocation> artifacts) {
    }
}
