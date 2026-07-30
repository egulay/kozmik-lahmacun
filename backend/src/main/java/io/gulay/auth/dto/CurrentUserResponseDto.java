package io.gulay.auth.dto;

import java.util.Set;

public record CurrentUserResponseDto(
        String userId,
        String username,
        String displayName,
        String email,
        Set<String> roles) {
}

