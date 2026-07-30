package io.gulay.user.dto;

import io.gulay.user.data.model.UserOperationStatus;
import io.gulay.user.data.model.UserRole;
import io.gulay.user.data.model.UserStatus;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Size;

import java.time.Instant;
import java.util.Set;
import java.util.UUID;

public final class UserManagementDtos {
    private UserManagementDtos() {
    }

    public record UserSummary(
            UUID id, String keycloakUserId, String username, String displayName,
            String email, UserStatus status, Set<UserRole> roles, Instant updatedAt) {
    }

    public record UserPage(
            java.util.List<UserSummary> users, int page, int size, long totalElements,
            int totalPages, boolean first, boolean last) {
    }

    public record UpdateUserRequest(
            @NotBlank @Size(min = 2, max = 100) String displayName,
            @Email @NotBlank @Size(max = 254) String email,
            @NotEmpty @Size(max = 1) Set<UserRole> roles) {
    }

    public record CreateUserRequest(
            @NotBlank @Size(min = 2, max = 100) String displayName,
            @Email @NotBlank @Size(max = 254) String email,
            @NotEmpty @Size(max = 1) Set<UserRole> roles) {
    }

    public record PasswordActionResponse(String status) {
    }

    public record OperationResponse(
            UUID operationId, UUID userId, UserOperationStatus status, String correlationId) {
    }
}
