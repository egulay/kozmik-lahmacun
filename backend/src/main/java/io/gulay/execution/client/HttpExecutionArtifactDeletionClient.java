package io.gulay.execution.client;

import java.util.List;
import java.util.UUID;
import java.time.Duration;

import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import tools.jackson.databind.ObjectMapper;
import io.gulay.executor.client.PythonExecutorTransport;

@Component
@RequiredArgsConstructor
public class HttpExecutionArtifactDeletionClient implements ExecutionArtifactDeletionClient {

    private final PythonExecutorTransport transport;
    private final ObjectMapper objectMapper;

    @Override
    public void delete(
            UUID executionId, String correlationId, List<ArtifactLocation> artifacts) {
        if (artifacts.isEmpty()) {
            return;
        }
        try {
            var body = objectMapper.writeValueAsString(
                    new DeleteRequest("1.0", executionId, artifacts));
            var response = transport.postJson("/internal/v1/artifacts/delete", body,
                    correlationId, Duration.ofSeconds(30));
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                throw new IllegalStateException("Executor artifact deletion failed");
            }
        } catch (RuntimeException exception) {
            throw exception;
        } catch (Exception exception) {
            throw new IllegalStateException("Executor artifact deletion failed", exception);
        }
    }

    private record DeleteRequest(
            String schemaVersion,
            UUID executionId,
            List<ArtifactLocation> artifacts) {
    }
}
