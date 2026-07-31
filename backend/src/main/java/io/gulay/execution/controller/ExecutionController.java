package io.gulay.execution.controller;

import lombok.val;

import io.gulay.execution.data.service.ExecutionLifecycleService;
import io.gulay.execution.data.service.ExecutionQueryService;
import io.gulay.execution.data.service.ReportPlanningService;
import io.gulay.execution.dto.ExecutionDtos;
import io.gulay.execution.dto.ResultDtos;
import io.gulay.execution.messaging.ExecutionEventHub;
import io.gulay.execution.result.data.service.ResultQueryService;
import io.gulay.security.PlatformRole;
import jakarta.validation.Valid;

import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;

import lombok.RequiredArgsConstructor;
import org.slf4j.MDC;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.DeleteMapping;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import io.gulay.execution.data.model.ExecutionStatus;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@RestController
@RequestMapping("/api/executions")
@RequiredArgsConstructor
public class ExecutionController {
    private final ReportPlanningService service;
    private final ExecutionQueryService queryService;
    private final ExecutionEventHub eventHub;
    private final ResultQueryService resultQueryService;
    private final ExecutionLifecycleService lifecycleService;
    private final io.gulay.execution.data.service.ExecutionDeletionService deletionService;

    @GetMapping
    ExecutionDtos.ExecutionListResponse list(
            @AuthenticationPrincipal OidcUser user,
            Authentication authentication,
            @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size,
            @RequestParam(required = false) Set<ExecutionStatus> status,
            @RequestParam(defaultValue = "") String search) {
        return queryService.list(
                user.getSubject(), page, size, status, search, roles(authentication));
    }

    @PostMapping("/report-plans")
    ResponseEntity<ExecutionDtos.ReportPlanResponse> create(
            @Valid @RequestBody ExecutionDtos.CreateReportPlanRequest request,
            @RequestHeader("Idempotency-Key") String idempotencyKey,
            @AuthenticationPrincipal OidcUser user,
            Authentication authentication) {
        if (!idempotencyKey.matches("[A-Za-z0-9._-]{1,100}")) {
            throw new IllegalArgumentException("Invalid idempotency key");
        }
        val response = service.create(request, idempotencyKey, user.getSubject(),
                roles(authentication), MDC.get("correlationId"));
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @PostMapping("/ml-plans")
    ResponseEntity<ExecutionDtos.ReportPlanResponse> createMl(
            @Valid @RequestBody ExecutionDtos.CreateReportPlanRequest request,
            @RequestHeader("Idempotency-Key") String idempotencyKey,
            @AuthenticationPrincipal OidcUser user,
            Authentication authentication) {
        if (!idempotencyKey.matches("[A-Za-z0-9._-]{1,100}")) {
            throw new IllegalArgumentException("Invalid idempotency key");
        }
        val response = service.createMl(request, idempotencyKey, user.getSubject(),
                roles(authentication), MDC.get("correlationId"));
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @GetMapping("/{executionId}")
    ExecutionDtos.ExecutionStateResponse state(
            @PathVariable java.util.UUID executionId,
            @AuthenticationPrincipal OidcUser user,
            Authentication authentication) {
        return queryService.state(executionId, user.getSubject(), roles(authentication));
    }

    @GetMapping(path = "/{executionId}/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    SseEmitter stream(
            @PathVariable java.util.UUID executionId,
            @AuthenticationPrincipal OidcUser user,
            Authentication authentication) {
        queryService.state(executionId, user.getSubject(), roles(authentication));
        return eventHub.subscribe(executionId);
    }

    @GetMapping("/{executionId}/result")
    ResultDtos.ResultResponse result(
            @PathVariable java.util.UUID executionId,
            @AuthenticationPrincipal OidcUser user,
            Authentication authentication,
            @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "20") @Min(1) @Max(50) int size) {
        return resultQueryService.result(
                executionId, user.getSubject(), roles(authentication), page, size);
    }

    @PostMapping("/{executionId}/cancel")
    ResponseEntity<Void> cancel(
            @PathVariable java.util.UUID executionId,
            @AuthenticationPrincipal OidcUser user,
            Authentication authentication) {
        lifecycleService.cancel(
                executionId, user.getSubject(), roles(authentication));
        return ResponseEntity.accepted().build();
    }

    @DeleteMapping("/{executionId}")
    ResponseEntity<ExecutionDtos.ExecutionDeletionResponse> delete(
            @PathVariable java.util.UUID executionId,
            @AuthenticationPrincipal OidcUser user,
            Authentication authentication) {
        val completed = deletionService.delete(
                executionId, user.getSubject(), roles(authentication),
                java.util.Optional.ofNullable(MDC.get("correlationId"))
                        .orElseGet(() -> java.util.UUID.randomUUID().toString()));
        val response = new ExecutionDtos.ExecutionDeletionResponse(
                ExecutionDtos.SCHEMA_VERSION, executionId,
                completed ? "COMPLETED" : "PENDING");
        return completed
                ? ResponseEntity.ok(response)
                : ResponseEntity.accepted().body(response);
    }

    private Set<PlatformRole> roles(Authentication authentication) {
        return authentication.getAuthorities().stream()
                .map(org.springframework.security.core.GrantedAuthority::getAuthority)
                .filter(Objects::nonNull)
                .map(authority -> authority.replaceFirst("^ROLE_", ""))
                .map(PlatformRole::fromKeycloakRole).flatMap(java.util.Optional::stream)
                .collect(Collectors.toSet());
    }
}
