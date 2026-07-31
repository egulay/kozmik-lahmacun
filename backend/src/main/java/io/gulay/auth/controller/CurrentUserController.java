package io.gulay.auth.controller;

import lombok.val;

import io.gulay.auth.dto.CurrentUserResponseDto;
import io.gulay.auth.data.service.WorkspaceGenerationService;
import io.gulay.security.PlatformRole;

import java.util.Set;
import java.util.TreeSet;
import java.util.Objects;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import lombok.RequiredArgsConstructor;

@RestController
@RequestMapping("/api/auth")
@RequiredArgsConstructor
public class CurrentUserController {
    private final WorkspaceGenerationService workspaceGenerationService;

    @GetMapping("/me")
    public CurrentUserResponseDto currentUser(@AuthenticationPrincipal OidcUser user) {
        val roles = new TreeSet<String>();
        user.getAuthorities().stream()
                .map(org.springframework.security.core.GrantedAuthority::getAuthority)
                .filter(Objects::nonNull)
                .filter(authority -> authority.startsWith("ROLE_"))
                .map(authority -> authority.substring("ROLE_".length()))
                .filter(role -> PlatformRole.fromKeycloakRole(role).isPresent())
                .forEach(roles::add);

        return new CurrentUserResponseDto(
                user.getSubject(),
                user.getPreferredUsername(),
                user.getFullName(),
                user.getEmail(),
                assignedPlatformRoles(roles),
                workspaceGenerationService.current());
    }

    /*
     * Keycloak expands composite roles in tokens (ADMIN includes SCIENTIST and
     * REPORTER). The UI displays assigned platform identity, not inherited
     * authorization capabilities, so expose only the highest platform role.
     */
    private Set<String> assignedPlatformRoles(Set<String> effectiveRoles) {
        if (effectiveRoles.contains(PlatformRole.ADMIN.name())) {
            return Set.of(PlatformRole.ADMIN.name());
        }
        if (effectiveRoles.contains(PlatformRole.SCIENTIST.name())) {
            return Set.of(PlatformRole.SCIENTIST.name());
        }
        if (effectiveRoles.contains(PlatformRole.REPORTER.name())) {
            return Set.of(PlatformRole.REPORTER.name());
        }
        return Set.of();
    }
}
