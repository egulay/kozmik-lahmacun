package io.gulay.api;

import java.time.Instant;
import java.util.List;
public record ApiError(
        String schemaVersion,
        String code,
        String message,
        String correlationId,
        Instant timestamp,
        List<FieldError> fieldErrors) {
    public record FieldError(String field, String code) {}
}
