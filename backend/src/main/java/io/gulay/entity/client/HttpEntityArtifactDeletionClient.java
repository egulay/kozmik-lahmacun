package io.gulay.entity.client;

import io.gulay.executor.client.PythonExecutorTransport;
import lombok.RequiredArgsConstructor;
import lombok.val;
import org.springframework.stereotype.Component;
import tools.jackson.databind.ObjectMapper;

import java.time.Duration;
import java.util.UUID;

@Component
@RequiredArgsConstructor
public class HttpEntityArtifactDeletionClient implements EntityArtifactDeletionClient {
    private final PythonExecutorTransport transport;
    private final ObjectMapper mapper;

    @Override
    public void delete(UUID entityId, String correlationId) {
        try {
            val body = mapper.writeValueAsString(new Request("1.0", entityId));
            val response = transport.postJson(
                    "/internal/v1/artifacts/entities/delete", body,
                    correlationId, Duration.ofMinutes(2));
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                throw new IllegalStateException("Executor entity artifact deletion failed");
            }
        } catch (RuntimeException exception) {
            throw exception;
        } catch (Exception exception) {
            throw new IllegalStateException("Executor entity artifact deletion failed", exception);
        }
    }

    private record Request(String schemaVersion, UUID entityId) { }
}
