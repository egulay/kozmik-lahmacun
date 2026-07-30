package io.gulay.health;

import java.net.URI;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.health.contributor.Health;
import org.springframework.boot.health.contributor.HealthIndicator;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component("keycloak")
public class KeycloakHealthIndicator implements HealthIndicator {

    private final RestClient restClient;
    private final URI realmUri;

    public KeycloakHealthIndicator(
            RestClient.Builder restClientBuilder,
            @Value("${kozmik.keycloak.realm-url}") URI realmUri) {
        this.restClient = restClientBuilder.build();
        this.realmUri = realmUri;
    }

    @Override
    public Health health() {
        try {
            restClient.get().uri(realmUri).retrieve().toBodilessEntity();
            return Health.up().withDetail("service", "keycloak").build();
        } catch (RuntimeException unavailable) {
            return Health.down().withDetail("service", "keycloak").build();
        }
    }
}
