package io.gulay.health.controller;

import lombok.val;

import io.gulay.health.data.service.ProviderHealthService;
import io.gulay.health.data.service.KafkaHealthService;

import java.time.Instant;
import java.util.List;

import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/health")
@RequiredArgsConstructor
public class ServiceStatusController {
    private final ProviderHealthService providerHealth;
    private final KafkaHealthService kafkaHealth;

    @GetMapping("/services")
    ServiceStatusResponse services() {
        val snapshot = providerHealth.check();
        return new ServiceStatusResponse(
                "1.0",
                Instant.now(),
                List.of(
                        new ServiceStatus("backend", "AVAILABLE", null, null),
                        new ServiceStatus("executor", snapshot.pythonStatus(), null,
                                "UNAVAILABLE".equals(snapshot.pythonStatus())
                                        ? "EXECUTOR_UNAVAILABLE" : null),
                        new ServiceStatus("llm", snapshot.providerStatus(), snapshot.model(),
                                snapshot.errorCode()),
                        new ServiceStatus("kafka", kafkaHealth.check(), null, null)));
    }

    record ServiceStatusResponse(
            String schemaVersion, Instant checkedAt, List<ServiceStatus> services) {
    }

    record ServiceStatus(String service, String status, String model, String errorCode) {
    }
}
