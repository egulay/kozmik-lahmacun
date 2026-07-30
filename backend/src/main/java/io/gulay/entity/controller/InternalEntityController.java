package io.gulay.entity.controller;

import io.gulay.entity.data.service.EntityManagementService;
import io.gulay.entity.dto.EntityDtos;
import io.gulay.security.PlatformRole;

import java.util.UUID;

import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import jakarta.validation.Valid;

@RestController
@RequestMapping("/internal/v1/entities")
@RequiredArgsConstructor
public class InternalEntityController {
    private final EntityManagementService service;

    @GetMapping("/{entityId}/schema")
    EntityDtos.EntitySchemaResponse schema(
            @PathVariable UUID entityId,
            @RequestParam UUID actorUserId,
            @RequestParam PlatformRole capability) {
        if (capability == PlatformRole.ADMIN) {
            capability = PlatformRole.SCIENTIST;
        }
        return service.internalSchema(entityId, actorUserId, capability);
    }

    @GetMapping("/{entityId}/ingestion-schema")
    EntityDtos.EntitySchemaResponse ingestionSchema(@PathVariable UUID entityId) {
        return service.internalIngestionSchema(entityId);
    }

    @PostMapping("/stream-registry/resolve")
    EntityDtos.EntitySchemaResponse resolveOrRegister(
            @Valid @RequestBody EntityDtos.StreamEntityDescriptor descriptor) {
        return service.resolveOrRegisterStreamEntity(descriptor);
    }
}
