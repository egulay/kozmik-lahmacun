package io.gulay.health.data.service;

import lombok.val;

import java.time.Duration;
import java.util.concurrent.TimeUnit;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.apache.kafka.clients.admin.AdminClient;
import org.springframework.kafka.core.KafkaAdmin;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
@Slf4j
public class KafkaHealthService {
    private static final Duration TIMEOUT = Duration.ofSeconds(2);

    private final KafkaAdmin kafkaAdmin;

    public String check() {
        try (val admin = AdminClient.create(kafkaAdmin.getConfigurationProperties())) {
            val clusterId = admin.describeCluster()
                    .clusterId()
                    .get(TIMEOUT.toMillis(), TimeUnit.MILLISECONDS);
            return clusterId == null || clusterId.isBlank() ? "UNAVAILABLE" : "AVAILABLE";
        } catch (Exception exception) {
            log.warn("Kafka event backbone health check failed: {}",
                    exception.getClass().getSimpleName());
            return "UNAVAILABLE";
        }
    }
}
