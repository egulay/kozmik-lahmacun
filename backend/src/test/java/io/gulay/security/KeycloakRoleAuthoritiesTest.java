package io.gulay.security;

import lombok.val;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class KeycloakRoleAuthoritiesTest {

    @Test
    void mapsOnlyKnownPlatformRoles() {
        val claims = Map.<String, Object>of(
                "realm_access",
                Map.of("roles", List.of("REPORTER", "SCIENTIST", "offline_access", 42)));

        assertThat(KeycloakRoleAuthorities.extract(claims))
                .extracting(org.springframework.security.core.GrantedAuthority::getAuthority)
                .containsExactly("ROLE_REPORTER", "ROLE_SCIENTIST");
    }

    @Test
    void returnsNoRolesForMalformedClaim() {
        assertThat(KeycloakRoleAuthorities.extract(Map.of("realm_access", "invalid"))).isEmpty();
        assertThat(KeycloakRoleAuthorities.extract(Map.of())).isEmpty();
    }
}
