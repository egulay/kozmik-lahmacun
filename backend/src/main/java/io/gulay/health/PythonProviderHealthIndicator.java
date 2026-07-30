package io.gulay.health;

import lombok.val;

import io.gulay.health.data.service.ProviderHealthService;
import lombok.RequiredArgsConstructor;
import org.springframework.boot.health.contributor.Health;
import org.springframework.boot.health.contributor.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("pythonProvider")
@RequiredArgsConstructor
public class PythonProviderHealthIndicator implements HealthIndicator {
    private final ProviderHealthService healthService;

    @Override
    public Health health() {
        val snapshot = healthService.check();
        val builder = "AVAILABLE".equals(snapshot.pythonStatus())
                && "AVAILABLE".equals(snapshot.providerStatus())
                ? Health.up() : Health.down();
        return builder.withDetail("service", "python-provider")
                .withDetail("provider", snapshot.provider() == null ? "unknown" : snapshot.provider())
                .build();
    }
}
