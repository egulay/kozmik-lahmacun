package io.gulay.execution.client;

import tools.jackson.databind.JsonNode;

public interface PythonReportPlanningClient {
    JsonNode plan(JsonNode request);

    JsonNode planMl(JsonNode request);
}
