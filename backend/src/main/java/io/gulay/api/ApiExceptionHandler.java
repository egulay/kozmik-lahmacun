package io.gulay.api;

import lombok.val;

import io.gulay.execution.ReportPlanningException;
import java.time.Clock;
import java.time.Instant;
import java.util.List;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.slf4j.MDC;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.orm.ObjectOptimisticLockingFailureException;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.server.ResponseStatusException;
@RestControllerAdvice
@RequiredArgsConstructor
@Slf4j
public class ApiExceptionHandler {
    private static final String VERSION = "1.0";
    private final Clock clock;

    @ExceptionHandler(ResourceNotFoundException.class)
    ResponseEntity<ApiError> notFound(ResourceNotFoundException exception) {
        warn("RESOURCE_NOT_FOUND", exception);
        return error(HttpStatus.NOT_FOUND, "RESOURCE_NOT_FOUND", exception.getMessage(), List.of());
    }

    @ExceptionHandler(ForbiddenOperationException.class)
    ResponseEntity<ApiError> forbidden(ForbiddenOperationException exception) {
        warn("ACCESS_DENIED", exception);
        return error(HttpStatus.FORBIDDEN, "ACCESS_DENIED", exception.getMessage(), List.of());
    }

    @ExceptionHandler(BadCredentialsException.class)
    ResponseEntity<ApiError> badCredentials(BadCredentialsException exception) {
        warn("AUTHENTICATION_FAILED", exception);
        return error(HttpStatus.UNAUTHORIZED, "AUTHENTICATION_FAILED",
                "Invalid username or password", List.of());
    }

    @ExceptionHandler({ConflictException.class, ObjectOptimisticLockingFailureException.class})
    ResponseEntity<ApiError> conflict(RuntimeException exception) {
        warn("RESOURCE_CONFLICT", exception);
        return error(HttpStatus.CONFLICT, "RESOURCE_CONFLICT", exception.getMessage(), List.of());
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ApiError> validation(MethodArgumentNotValidException exception) {
        warn("VALIDATION_FAILED", exception);
        val fields = exception.getBindingResult().getFieldErrors().stream()
                .map(field -> new ApiError.FieldError(
                        field.getField(), field.getCode() == null ? "INVALID" : field.getCode()))
                .toList();
        return error(HttpStatus.BAD_REQUEST, "VALIDATION_FAILED",
                "The request failed validation", fields);
    }

    @ExceptionHandler({HttpMessageNotReadableException.class, MethodArgumentTypeMismatchException.class})
    ResponseEntity<ApiError> malformed(Exception exception) {
        warn("INVALID_REQUEST", exception);
        return error(HttpStatus.BAD_REQUEST, "INVALID_REQUEST",
                "The request could not be parsed", List.of());
    }

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<ApiError> illegalArgument(IllegalArgumentException exception) {
        warn("INVALID_REQUEST", exception);
        return error(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", exception.getMessage(), List.of());
    }

    @ExceptionHandler(ReportPlanningException.class)
    ResponseEntity<ApiError> invalidOrder(ReportPlanningException exception) {
        warn("REPORT_ORDER_INVALID", exception);
        return error(HttpStatus.UNPROCESSABLE_CONTENT, "REPORT_ORDER_INVALID",
                exception.getMessage(), List.of());
    }

    @ExceptionHandler(ResponseStatusException.class)
    ResponseEntity<ApiError> responseStatus(ResponseStatusException exception) {
        val status = HttpStatus.valueOf(exception.getStatusCode().value());
        val code = status == HttpStatus.TOO_MANY_REQUESTS
                ? "SSE_SUBSCRIBER_LIMIT_REACHED"
                : "REQUEST_REJECTED";
        warn(code, exception);
        return error(status, code,
                exception.getReason() == null ? "The request was rejected" : exception.getReason(),
                List.of());
    }

    @ExceptionHandler(Exception.class)
    ResponseEntity<ApiError> unexpected(Exception exception) {
        log.error("api_request_failed code=INTERNAL_ERROR exceptionType={}",
                exception.getClass().getSimpleName(), exception);
        return error(HttpStatus.INTERNAL_SERVER_ERROR, "INTERNAL_ERROR",
                "An unexpected error occurred", List.of());
    }

    private void warn(String code, Exception exception) {
        log.warn("api_request_rejected code={} exceptionType={}",
                code, exception.getClass().getSimpleName());
    }

    private ResponseEntity<ApiError> error(
            HttpStatus status, String code, String message, List<ApiError.FieldError> fields) {
        val correlationId = MDC.get("correlationId");
        return ResponseEntity.status(status).body(new ApiError(
                VERSION, code, message, correlationId, Instant.now(clock), fields));
    }
}
