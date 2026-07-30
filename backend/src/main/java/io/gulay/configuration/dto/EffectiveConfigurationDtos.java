package io.gulay.configuration.dto;


public final class EffectiveConfigurationDtos {
    private EffectiveConfigurationDtos() {
    }

    public record LlmProviderConfiguration(
            String provider,
            String baseUrl,
            String model,
            int timeoutSeconds,
            int maxRetries,
            int maxContextMessages,
            int maxContextCharacters) {
    }

    public record EffectiveConfiguration(
            String schemaVersion, LlmProviderConfiguration llm,
            SparkExecutionConfiguration execution) {
    }

    public record SparkExecutionConfiguration(
            int timeoutSeconds, int maxConcurrentJobs, int maxPreviewRows,
            String datasetUri, String datasetFormat) {
    }
}
