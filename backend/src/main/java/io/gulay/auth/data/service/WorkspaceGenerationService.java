package io.gulay.auth.data.service;

import lombok.RequiredArgsConstructor;
import lombok.val;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
public class WorkspaceGenerationService {
    private final JdbcTemplate jdbcTemplate;

    @Transactional(readOnly = true)
    public String current() {
        val generation = jdbcTemplate.queryForObject(
                """
                SELECT md5(current_database() || ':' || MIN(installed_on)::text)
                FROM flyway_schema_history
                """,
                String.class);
        if (generation == null || generation.isBlank()) {
            throw new IllegalStateException("Workspace generation is unavailable");
        }
        return generation;
    }
}
