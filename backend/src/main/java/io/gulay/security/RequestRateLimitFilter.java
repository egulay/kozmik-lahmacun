package io.gulay.security;

import lombok.val;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import java.io.IOException;
import java.time.Clock;
import java.time.Instant;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import org.jspecify.annotations.NonNull;

@Component
@RequiredArgsConstructor
public class RequestRateLimitFilter extends OncePerRequestFilter {
    private final Clock clock;
    private final Map<String, Window> windows = new ConcurrentHashMap<>();

    @Value("${kozmik.security.mutation-rate-limit-per-minute:60}")
    private int limit;

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !"POST".equals(request.getMethod())
                || !request.getRequestURI().startsWith("/api/");
    }

    @Override
    protected void doFilterInternal(
            @NonNull HttpServletRequest request,
            @NonNull HttpServletResponse response,
            @NonNull FilterChain chain)
            throws ServletException, IOException {
        val authentication = SecurityContextHolder.getContext().getAuthentication();
        val identity = authentication != null && authentication.isAuthenticated()
                ? authentication.getName() : request.getRemoteAddr();
        val now = Instant.now(clock).getEpochSecond();
        val windowStart = now - now % 60;
        val accepted = windows.compute(identity, (key, current) ->
                current == null || current.startedAt() != windowStart
                        ? new Window(windowStart, 1)
                        : new Window(windowStart, current.count() + 1));
        if (accepted.count() > limit) {
            response.setStatus(429);
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.getWriter().write(
                    "{\"schemaVersion\":\"1.0\",\"code\":\"RATE_LIMIT_EXCEEDED\"}");
            return;
        }
        if (windows.size() > 10_000) {
            windows.entrySet().removeIf(entry -> entry.getValue().startedAt() < windowStart);
        }
        chain.doFilter(request, response);
    }

    private record Window(long startedAt, int count) {
    }
}
