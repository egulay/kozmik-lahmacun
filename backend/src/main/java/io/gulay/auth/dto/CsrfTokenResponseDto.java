package io.gulay.auth.dto;

public record CsrfTokenResponseDto(String headerName, String parameterName, String token) {
}
