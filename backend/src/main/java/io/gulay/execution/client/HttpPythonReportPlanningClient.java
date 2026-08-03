package io.gulay.execution.client;

import lombok.val;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import io.gulay.execution.ReportPlanningException;

import java.time.Duration;

import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import io.gulay.executor.client.PythonExecutorTransport;

@Component
@RequiredArgsConstructor
public class HttpPythonReportPlanningClient implements PythonReportPlanningClient {
    private final ObjectMapper objectMapper;
    private final PythonExecutorTransport transport;
    @Value("${kozmik.python.planning-timeout-seconds:660}")
    private long planningTimeoutSeconds;

    @Override
    public JsonNode plan(JsonNode request) {
        return call(request, "/internal/v1/plans/report");
    }

    @Override
    public JsonNode planMl(JsonNode request) {
        return call(request, "/internal/v1/plans/ml");
    }

    private JsonNode call(JsonNode request, String path) {
        try {
            val response = transport.postJson(path, objectMapper.writeValueAsString(request),
                    safeText(request.path("correlationId")),
                    Duration.ofSeconds(planningTimeoutSeconds));
            if (response.statusCode() == 422) {
                throw new ReportPlanningException(validationMessage(response.body()));
            }
            if (response.statusCode() != 200) {
                throw new IllegalStateException("Python report planning endpoint unavailable");
            }
            return objectMapper.readTree(response.body());
        } catch (ReportPlanningException exception) {
            throw exception;
        } catch (Exception exception) {
            throw new IllegalStateException("Python report planning failed", exception);
        }
    }

    private String validationMessage(String body) {
        try {
            val detail = objectMapper.readTree(body).path("detail");
            val issues = detail.path("issues");
            if (issues.isArray() && !issues.isEmpty()) {
                val message = textOrNull(issues.get(0).path("message"));
                if (message != null && !message.isBlank()) {
                    return message.length() <= 300 ? message : message.substring(0, 300);
                }
            }
            val code = textOrNull(detail.path("code"));
            return code == null || code.isBlank()
                    ? "Generated order failed governed validation" : code;
        } catch (Exception ignored) {
            return "Generated order failed governed validation";
        }
    }

    private String safeText(JsonNode value) {
        val text = textOrNull(value);
        return text == null ? "" : text;
    }

    private String textOrNull(JsonNode value) {
        return value != null && value.isString() ? value.stringValue() : null;
    }
}
