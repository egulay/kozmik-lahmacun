package io.gulay.entity.controller;

import lombok.val;

import io.gulay.entity.data.service.EntityManagementService;
import io.gulay.entity.dto.EntityDtos;
import jakarta.validation.Valid;

import java.net.URI;
import java.util.UUID;

import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/admin/entities")
@RequiredArgsConstructor
public class AdminEntityController {
    private final EntityManagementService service;

    @org.springframework.web.bind.annotation.PostMapping
    ResponseEntity<EntityDtos.EntitySummary> create(
            @Valid @RequestBody EntityDtos.CreateEntityRequest request,
            @AuthenticationPrincipal OidcUser user) {
        val created = service.create(request, user.getSubject());
        return ResponseEntity.created(URI.create("/api/entities/" + created.id())).body(created);
    }

    @PutMapping("/{entityId}")
    EntityDtos.EntitySummary update(
            @PathVariable UUID entityId,
            @Valid @RequestBody EntityDtos.UpdateEntityRequest request) {
        return service.update(entityId, request);
    }

}
