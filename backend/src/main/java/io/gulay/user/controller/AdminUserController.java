package io.gulay.user.controller;

import io.gulay.user.data.service.UserManagementService;
import io.gulay.user.dto.UserManagementDtos;
import jakarta.validation.Valid;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/admin/users")
@RequiredArgsConstructor
public class AdminUserController {
    private final UserManagementService service;

    @GetMapping
    UserManagementDtos.UserPage list(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        return service.list(page, size);
    }

    @PostMapping
    UserManagementDtos.UserSummary create(
            @Valid @RequestBody UserManagementDtos.CreateUserRequest request,
            @AuthenticationPrincipal OidcUser actor) {
        return service.create(request, actor.getSubject());
    }

    @PutMapping("/{userId}")
    UserManagementDtos.OperationResponse update(
            @PathVariable UUID userId,
            @Valid @RequestBody UserManagementDtos.UpdateUserRequest request,
            @AuthenticationPrincipal OidcUser actor) {
        return service.update(userId, request, actor.getSubject());
    }

    @PostMapping("/{userId}/suspend")
    UserManagementDtos.OperationResponse suspend(
            @PathVariable UUID userId, @AuthenticationPrincipal OidcUser actor) {
        return service.suspend(userId, actor.getSubject());
    }

    @PostMapping("/{userId}/resume")
    UserManagementDtos.OperationResponse resume(
            @PathVariable UUID userId, @AuthenticationPrincipal OidcUser actor) {
        return service.resume(userId, actor.getSubject());
    }

    @PostMapping("/{userId}/password-reset")
    UserManagementDtos.PasswordActionResponse resetPassword(
            @PathVariable UUID userId, @AuthenticationPrincipal OidcUser actor) {
        return service.resetPassword(userId, actor.getSubject());
    }

    @DeleteMapping("/{userId}")
    UserManagementDtos.OperationResponse delete(
            @PathVariable UUID userId, @AuthenticationPrincipal OidcUser actor) {
        return service.delete(userId, actor.getSubject());
    }
}
