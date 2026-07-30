package io.gulay.entity.controller;

import io.gulay.entity.data.service.EntityManagementService;
import io.gulay.entity.dto.EntityDtos;
import io.gulay.ingestion.IngestionEventHub;
import io.gulay.security.PlatformRole;

import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;

import lombok.RequiredArgsConstructor;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestHeader;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.http.MediaType;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@RestController
@RequestMapping("/api/entities")
@RequiredArgsConstructor
public class EntityController {
    private final EntityManagementService service;
    private final IngestionEventHub ingestionEventHub;

    @GetMapping
    EntityDtos.EntityListResponse list(
            @AuthenticationPrincipal OidcUser user, Authentication authentication,
            @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size,
            @RequestHeader(name = "Accept-Language", defaultValue = "en") String language) {
        return service.list(user.getSubject(), roles(authentication), page, size, language);
    }

    @GetMapping(path = "/ingestion-stream",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    SseEmitter allIngestionActivity(@AuthenticationPrincipal OidcUser user) {
        if (user == null || user.getSubject() == null) {
            throw new IllegalArgumentException("Authenticated user is required");
        }
        return ingestionEventHub.subscribeAll();
    }

    @GetMapping("/{entityId}/schema")
    EntityDtos.EntitySchemaResponse currentSchema(
            @PathVariable UUID entityId,
            @AuthenticationPrincipal OidcUser user,
            Authentication authentication,
            @RequestHeader(name = "Accept-Language", defaultValue = "en") String language) {
        return service.currentSchema(
                entityId, user.getSubject(), roles(authentication), language);
    }

    @GetMapping("/{entityId}")
    EntityDtos.EntitySummary entity(
            @PathVariable UUID entityId,
            @AuthenticationPrincipal OidcUser user,
            Authentication authentication,
            @RequestHeader(name = "Accept-Language", defaultValue = "en") String language) {
        return service.get(entityId, user.getSubject(), roles(authentication), language);
    }

    @GetMapping("/{entityId}/schema/columns")
    EntityDtos.ColumnPageResponse currentSchemaColumns(
            @PathVariable UUID entityId,
            @AuthenticationPrincipal OidcUser user,
            Authentication authentication,
            @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size,
            @RequestHeader(name = "Accept-Language", defaultValue = "en") String language) {
        return service.currentSchemaColumns(
                entityId, user.getSubject(), roles(authentication), page, size, language);
    }

    @GetMapping(path = "/{entityId}/ingestion-stream",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    SseEmitter ingestionStream(
            @PathVariable UUID entityId,
            @AuthenticationPrincipal OidcUser user,
            Authentication authentication) {
        service.currentSchema(entityId, user.getSubject(), roles(authentication));
        return ingestionEventHub.subscribe(entityId);
    }

    private Set<PlatformRole> roles(Authentication authentication) {
        return authentication.getAuthorities().stream()
                .map(org.springframework.security.core.GrantedAuthority::getAuthority)
                .filter(Objects::nonNull)
                .map(authority -> authority.replaceFirst("^ROLE_", ""))
                .map(PlatformRole::fromKeycloakRole)
                .flatMap(java.util.Optional::stream)
                .collect(Collectors.toSet());
    }
}
