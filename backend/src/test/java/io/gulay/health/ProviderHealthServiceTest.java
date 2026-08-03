package io.gulay.health;

import lombok.val;

import com.sun.net.httpserver.HttpServer;
import io.gulay.health.data.service.ProviderHealthService;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;
import io.gulay.executor.client.PythonExecutorTransport;
import static org.assertj.core.api.Assertions.assertThat;

class ProviderHealthServiceTest {
    @Test
    void aggregatesSanitizedPythonAndProviderHealth() throws Exception {
        val server = HttpServer.create(new InetSocketAddress(0), 0);
        server.createContext("/internal/v1/health", exchange -> {
            assertThat(exchange.getRequestHeaders().getFirst("X-Internal-API-Key"))
                    .isEqualTo("internal-test-key");
            val body = """
                    {"status":"AVAILABLE","providerStatus":"AVAILABLE","provider":"lm-studio",
                     "model":"qwen-test","errorCode":null}
                    """.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, body.length);
            exchange.getResponseBody().write(body);
            exchange.close();
        });
        server.start();
        try {
            val service = new ProviderHealthService(
                    new PythonExecutorTransport(
                            "http://localhost:" + server.getAddress().getPort(),
                            "internal-test-key"), JsonMapper.builder().build());

            assertThat(service.check()).isEqualTo(
                    new ProviderHealthService.Snapshot(
                            "AVAILABLE", "AVAILABLE", "lm-studio", "qwen-test", null));
        } finally {
            server.stop(0);
        }
    }

    @Test
    void doesNotAttemptHealthWithoutInternalCredential() {
        val service = new ProviderHealthService(
                new PythonExecutorTransport("http://localhost:1", ""),
                JsonMapper.builder().build());

        assertThat(service.check()).isEqualTo(
                new ProviderHealthService.Snapshot(
                        "UNKNOWN", "UNKNOWN", null, null, null));
    }
}
