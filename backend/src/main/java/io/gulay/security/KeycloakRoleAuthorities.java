package io.gulay.security;

import lombok.val;

import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public final class KeycloakRoleAuthorities {

    private KeycloakRoleAuthorities() {
    }

    public static Set<GrantedAuthority> extract(Map<String, Object> claims) {
        val authorities = new LinkedHashSet<GrantedAuthority>();
        val realmAccess = claims.get("realm_access");
        if (!(realmAccess instanceof Map<?, ?> realmAccessMap)) {
            return authorities;
        }
        val roles = realmAccessMap.get("roles");
        if (!(roles instanceof Collection<?> roleValues)) {
            return authorities;
        }
        roleValues.stream()
                .filter(String.class::isInstance)
                .map(String.class::cast)
                .map(PlatformRole::fromKeycloakRole)
                .flatMap(java.util.Optional::stream)
                .map(PlatformRole::authority)
                .map(SimpleGrantedAuthority::new)
                .forEach(authorities::add);
        return authorities;
    }
}
