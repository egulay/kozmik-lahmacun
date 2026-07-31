package io.gulay.configuration.data.service;

import lombok.val;

import io.gulay.configuration.dto.EffectiveConfigurationDtos;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class EffectiveConfigurationService {
    @Value("${kozmik.llm.provider:LM_STUDIO}")
    private String defaultProvider;
    @Value("${kozmik.llm.base-url:http://localhost:1234/v1}")
    private String defaultBaseUrl;
    @Value("${kozmik.llm.model:local-model}")
    private String defaultModel;
    @Value("${kozmik.llm.timeout-seconds:60}")
    private int defaultTimeout;
    @Value("${kozmik.llm.max-retries:2}")
    private int defaultRetries;
    @Value("${kozmik.llm.max-context-messages:20}")
    private int defaultMessages;
    @Value("${kozmik.llm.max-context-characters:12000}")
    private int defaultCharacters;
    @Value("${kozmik.execution.timeout-seconds:1800}")
    private int executionTimeout;
    @Value("${kozmik.execution.max-concurrent-jobs:4}")
    private int maxConcurrentJobs;
    @Value("${kozmik.execution.max-preview-rows:100}")
    private int maxPreviewRows;
    @Value("${kozmik.execution.dataset-uri:}")
    private String datasetUri;
    @Value("${kozmik.execution.dataset-format:parquet}")
    private String datasetFormat;

    public EffectiveConfigurationDtos.EffectiveConfiguration effective() {
        val llm = new EffectiveConfigurationDtos.LlmProviderConfiguration(
                defaultProvider, defaultBaseUrl, defaultModel,
                defaultTimeout, defaultRetries, defaultMessages, defaultCharacters);
        val execution = new EffectiveConfigurationDtos.SparkExecutionConfiguration(
                executionTimeout, maxConcurrentJobs, maxPreviewRows, datasetUri, datasetFormat);
        return new EffectiveConfigurationDtos.EffectiveConfiguration("1.0", llm, execution);
    }
}
