package io.gulay.security;

import java.util.Arrays;
import java.util.Optional;

public enum PlatformRole {
    REPORTER,
    SCIENTIST,
    ADMIN;

    public String authority() {
        return "ROLE_" + name();
    }

    public static Optional<PlatformRole> fromKeycloakRole(String role) {
        return Arrays.stream(values()).filter(candidate -> candidate.name().equals(role)).findFirst();
    }
}

