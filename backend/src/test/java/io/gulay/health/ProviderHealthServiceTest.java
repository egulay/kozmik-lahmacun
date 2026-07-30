package io.gulay.health;

import lombok.val;

import com.sun.net.httpserver.HttpServer;
import io.gulay.health.data.service.ProviderHealthService;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.web.client.RestClient;
import static org.assertj.core.api.Assertions.assertThat;

class ProviderHealthServiceTest {
    @Test
    void aggregatesSanitizedPythonAndProviderHealth() throws Exception {
        val server = HttpServer.create(new InetSocketAddress(0), 0);
        server.createContext("/internal/v1/health", exchange -> {
            assertThat(exchange.getRequestHeaders().getFirst("X-Internal-API-Key"))
                    .isEqualTo("internal-test-key");
            val body = """
                    {"status":"AVAILABLE","providerStatus":"AVAILABLE","provider":"lm-studio"}
                    """.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, body.length);
            exchange.getResponseBody().write(body);
            exchange.close();
        });
        server.start();
        try {
            val service = new ProviderHealthService(
                    RestClient.builder(),
                    "http://localhost:" + server.getAddress().getPort(),
                    "internal-test-key");

            assertThat(service.check()).isEqualTo(
                    new ProviderHealthService.Snapshot(
                            "AVAILABLE", "AVAILABLE", "lm-studio"));
        } finally {
            server.stop(0);
        }
    }

    @Test
    void doesNotAttemptHealthWithoutInternalCredential() {
        val service = new ProviderHealthService(
                RestClient.builder(), "http://localhost:1", "");

        assertThat(service.check()).isEqualTo(
                new ProviderHealthService.Snapshot("UNKNOWN", "UNKNOWN", null));
    }
}
