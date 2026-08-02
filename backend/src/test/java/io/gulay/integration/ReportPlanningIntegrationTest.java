package io.gulay.integration;

import lombok.val;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import io.gulay.entity.data.model.ColumnDataType;
import io.gulay.entity.data.model.EntityStatus;
import io.gulay.entity.data.service.EntityManagementService;
import io.gulay.entity.dto.EntityDtos;
import io.gulay.execution.client.PythonReportPlanningClient;
import io.gulay.execution.client.ExecutionArtifactDeletionClient;
import io.gulay.execution.data.service.ReportPlanningService;
import io.gulay.execution.dto.ExecutionDtos;
import io.gulay.execution.messaging.KafkaMessageSigner;
import io.gulay.security.PlatformRole;
import io.gulay.user.data.model.AppUserReferenceModel;
import io.gulay.user.data.repository.AppUserReferenceRepository;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.kafka.KafkaContainer;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.DockerImageName;

@SpringBootTest
@AutoConfigureMockMvc
@Testcontainers
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ReportPlanningIntegrationTest {
    @Container static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer(DockerImageName.parse("postgres:16.4-alpine3.20"))
                    .withDatabaseName("kozmik").withUsername("kozmik").withPassword("test");
    @Container static final GenericContainer<?> REDIS =
            new GenericContainer<>(DockerImageName.parse("redis:7.2.5-alpine3.20"))
                    .withExposedPorts(6379);
    @Container static final KafkaContainer KAFKA =
            new KafkaContainer(DockerImageName.parse("apache/kafka-native:3.9.1"));

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRES::getUsername);
        registry.add("spring.datasource.password", POSTGRES::getPassword);
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add("spring.data.redis.port", () -> REDIS.getMappedPort(6379));
        registry.add("spring.data.redis.password", () -> "");
        registry.add("spring.security.oauth2.client.registration.keycloak.client-secret", () -> "x");
        registry.add("kozmik.security.internal-api-key", () -> "internal");
        registry.add("kozmik.security.kafka-message-signing-key",
                () -> "integration-test-kafka-signing-key-at-least-32-bytes");
        registry.add("server.servlet.session.cookie.secure", () -> "false");
        registry.add("spring.kafka.bootstrap-servers", KAFKA::getBootstrapServers);
        registry.add("kozmik.kafka.outbox-poll-ms", () -> "100");
        registry.add("kozmik.kafka.outbox-enabled", () -> "true");
        registry.add("spring.kafka.listener.auto-startup", () -> "true");
    }

    @Autowired MockMvc mockMvc;
    @Autowired ObjectMapper mapper;
    @Autowired EntityManagementService entityService;
    @Autowired ReportPlanningService planningService;
    @Autowired AppUserReferenceRepository users;
    @Autowired JdbcTemplate jdbc;
    @Autowired org.springframework.kafka.core.KafkaTemplate<String, String> kafka;
    @Autowired KafkaMessageSigner messageSigner;
    @MockitoBean PythonReportPlanningClient python;
    @MockitoBean ExecutionArtifactDeletionClient artifactDeletionClient;
    @MockitoBean org.springframework.security.oauth2.jwt.JwtDecoder jwtDecoder;
    @MockitoBean org.springframework.security.oauth2.client.registration.ClientRegistrationRepository
            clientRegistrationRepository;

    AppUserReferenceModel reporter;
    EntityDtos.EntitySummary entity;
    EntityDtos.EntitySchemaResponse schema;

    @Test
    void pendingExecutionIsVisibleBeforeBackgroundPlanningCompletes() {
        val request = new ExecutionDtos.CreateReportPlanRequest(
                entity.id(), "Total amount", "en");
        val pending = planningService.createPending(
                request, "pending-" + UUID.randomUUID(), reporter.getKeycloakUserId(),
                java.util.Set.of(PlatformRole.REPORTER), "pending-correlation", "REPORT");

        assertThat(pending.status()).isEqualTo("PLANNING");
        assertThat(pending.order().isEmpty()).isTrue();
        assertThat(jdbc.queryForObject(
                "select status from kozmik_lahmacun.execution_request where id = ?",
                String.class, pending.id())).isEqualTo("PLANNING");

        val completed = planningService.completePending(
                pending.id(), reporter.getKeycloakUserId(),
                java.util.Set.of(PlatformRole.REPORTER));

        assertThat(completed.status()).isEqualTo("VALIDATED");
        assertThat(completed.order().path("executionType").stringValue()).isEqualTo("REPORT");
    }

    @Test
    void administratorListsAndOpensExecutionsOwnedByOtherUsers() throws Exception {
        val pending = planningService.createPending(
                new ExecutionDtos.CreateReportPlanRequest(
                        entity.id(), "Admin-visible report", "en"),
                "admin-list-" + UUID.randomUUID(), reporter.getKeycloakUserId(),
                java.util.Set.of(PlatformRole.REPORTER), "admin-list-correlation", "REPORT");
        val adminLogin = oidcLogin()
                .idToken(token -> token.subject("independent-admin"))
                .authorities(new SimpleGrantedAuthority(PlatformRole.ADMIN.authority()));

        mockMvc.perform(get("/api/executions")
                .param("page", "0").param("size", "5")
                        .param("search", "Admin-visible report")
                        .with(adminLogin))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.executions[0].id").value(pending.id().toString()))
                .andExpect(jsonPath("$.totalElements").value(1));
        mockMvc.perform(get("/api/executions/{id}", pending.id())
                        .with(adminLogin))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(pending.id().toString()));
    }

    @BeforeEach
    void setup() {
        val now = Instant.now();
        val admin = users.save(AppUserReferenceModel.builder().id(UUID.randomUUID())
                .keycloakUserId("admin-" + UUID.randomUUID()).createdAt(now).updatedAt(now).build());
        reporter = users.save(AppUserReferenceModel.builder().id(UUID.randomUUID())
                .keycloakUserId("reporter-" + UUID.randomUUID()).createdAt(now).updatedAt(now).build());
        entity = entityService.create(new EntityDtos.CreateEntityRequest(
                "Orders-" + UUID.randomUUID(), null, EntityStatus.ACTIVE),
                admin.getKeycloakUserId());
        schema = entityService.resolveOrRegisterStreamEntity(
                new EntityDtos.StreamEntityDescriptor(
                        entity.id(), entity.name(), entity.description(), List.of(
                        new EntityDtos.ColumnDefinition(null, "amount", "Amount",
                                ColumnDataType.DECIMAL, null, 1))));
        when(python.plan(any())).thenAnswer(invocation -> {
            val input = invocation.getArgument(0, tools.jackson.databind.JsonNode.class);
            val order = mapper.createObjectNode();
            order.put("schemaVersion", "1.0").put("executionType", "REPORT")
                    .put("entityId", entity.id().toString())
                    .put("requestedLanguage", "en").put("requestSummary", "Amounts");
            order.putObject("constraints").put("maxPreviewRows", 100).put("timeoutSeconds", 300);
            val payload = order.putObject("payload");
            payload.putArray("select").addObject().put("column", "amount");
            payload.putArray("filters"); payload.putArray("groupBy");
            payload.putArray("aggregations"); payload.putArray("orderBy");
            payload.put("limit", 100); payload.putArray("chartHints");
            return mapper.createObjectNode().set("order", order);
        });
        when(python.planMl(any())).thenAnswer(invocation -> {
            val order = mapper.createObjectNode();
            order.put("schemaVersion", "1.0").put("executionType", "ML")
                    .put("entityId", entity.id().toString())
                    .put("requestedLanguage", "en").put("requestSummary", "Amount model");
            order.putObject("constraints").put("maxPreviewRows", 20).put("timeoutSeconds", 300);
            val payload = order.putObject("payload");
            payload.put("problemType", "REGRESSION").put("algorithm", "LINEAR_REGRESSION")
                    .put("targetColumn", "amount");
            payload.putArray("featureColumns").add("amount");
            payload.putArray("filters");
            payload.putObject("split").put("strategy", "RANDOM")
                    .put("trainingRatio", 0.8).put("seed", 42);
            payload.putObject("parameters").put("maxIter", 20);
            payload.putArray("metrics").add("RMSE");
            payload.putObject("output").put("includeFeatureImportance", true)
                    .put("includePredictionsPreview", true);
            return mapper.createObjectNode().set("order", order);
        });
    }

    @Test
    void createsImmutablePlanAndInitialHistoryIdempotently() throws Exception {
        val body = """
                {"entityId":"%s","request":"Show amounts","language":"en"}
                """.formatted(entity.id());
        val first = mockMvc.perform(post("/api/executions/report-plans").with(csrf()).with(login())
                        .header("Idempotency-Key", "stable-key").contentType("application/json")
                        .content(body))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.status").value("VALIDATED"))
                .andExpect(jsonPath("$.order.executionType").value("REPORT"))
                .andReturn().getResponse().getContentAsString();
        val executionId = UUID.fromString(mapper.readTree(first).path("id").stringValue());
        mockMvc.perform(post("/api/executions/report-plans").with(csrf()).with(login())
                        .header("Idempotency-Key", "stable-key").contentType("application/json")
                        .content(body))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value(executionId.toString()));
        assertThat(jdbc.queryForObject(
                "select count(*) from execution_status_history where execution_id=?",
                Long.class, executionId)).isEqualTo(1L);
        verify(python, times(1)).plan(any());
        org.assertj.core.api.Assertions.assertThatThrownBy(() -> jdbc.update(
                "update execution_request set execution_order_json='{}'::jsonb where id=?",
                executionId)).hasMessageContaining("immutable");
    }

    @Test
    void ownerPhysicallyDeletesTerminalExecutionResultAndArtifactMetadata() throws Exception {
        val body = """
                {"entityId":"%s","request":"Delete after completion","language":"en"}
                """.formatted(entity.id());
        val response = mockMvc.perform(post("/api/executions/report-plans")
                        .with(csrf()).with(login())
                        .header("Idempotency-Key", "delete-" + UUID.randomUUID())
                        .contentType("application/json").content(body))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();
        val executionId = UUID.fromString(mapper.readTree(response).path("id").stringValue());
        val resultId = UUID.randomUUID();
        val artifactId = UUID.randomUUID();
        jdbc.update("""
                update execution_request
                set status='SUCCEEDED', completed_at=now()
                where id=?
                """, executionId);
        jdbc.update("""
                insert into execution_result
                (id, execution_id, schema_version, row_count, preview_json, kpis_json,
                 charts_json, warnings_json, management_summary, summary_status,
                 summary_evidence_json, summary_validation_status,
                 summary_validation_issues_json, summary_evidence_schema_version,
                 summary_audit_json, summary_blocking_issues_json,
                 summary_advisory_issues_json, summary_repair_attempt_count,
                 summary_provider, summary_provider_model, summary_generated_at, created_at)
                values (?, ?, '1.0', 1, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb,
                        '[]'::jsonb, 'Done', 'COMPLETED',
                        '{"schemaVersion":"2.0","semanticRegistryVersion":"1.0"}'::jsonb,
                        'ACCEPTED', '[]'::jsonb, '2.0',
                        '{"schemaVersion":"2.0","language":"en","prose":"Done","evidenceIds":["result.row-count"],"scope":{}}'::jsonb,
                        '[]'::jsonb, '[]'::jsonb,
                        0, 'test', 'test-model', now(), now())
                """, resultId, executionId);
        jdbc.update("""
                insert into execution_artifact
                (id, execution_result_id, format, bucket_name, object_key, created_at)
                values (?, ?, 'PARQUET', 'results', ?, now())
                """, artifactId, resultId,
                "executions/" + executionId + "/" + artifactId + ".parquet");

        mockMvc.perform(delete("/api/executions/{id}", executionId)
                        .with(csrf()).with(login()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("COMPLETED"));

        verify(artifactDeletionClient).delete(
                org.mockito.ArgumentMatchers.eq(executionId),
                org.mockito.ArgumentMatchers.anyString(),
                org.mockito.ArgumentMatchers.argThat(items ->
                        items.size() == 1
                                && items.get(0).artifactId().equals(artifactId)));
        assertThat(jdbc.queryForObject(
                "select count(*) from execution_request where id=?",
                Long.class, executionId)).isZero();
        assertThat(jdbc.queryForObject(
                "select count(*) from execution_result where id=?",
                Long.class, resultId)).isZero();
        assertThat(jdbc.queryForObject(
                "select count(*) from execution_artifact where id=?",
                Long.class, artifactId)).isZero();
        assertThat(jdbc.queryForObject(
                """
                select status from execution_deletion_job
                where execution_id=?
                """, String.class, executionId)).isEqualTo("COMPLETED");
        assertThat(jdbc.queryForObject(
                """
                select count(*) from audit_event
                where event_type='EXECUTION_DELETE_COMPLETED' and subject_id=?
                  and outcome='SUCCEEDED'
                """, Long.class, executionId.toString())).isEqualTo(1L);
    }

    @Test
    void rejectsIdempotencyKeyReuseWithDifferentRequest() throws Exception {
        val template = "{\"entityId\":\"%s\",\"request\":\"%s\",\"language\":\"en\"}";
        mockMvc.perform(post("/api/executions/report-plans").with(csrf()).with(login())
                        .header("Idempotency-Key", "conflict-key").contentType("application/json")
                        .content(template.formatted(entity.id(), "First")))
                .andExpect(status().isCreated());
        mockMvc.perform(post("/api/executions/report-plans").with(csrf()).with(login())
                        .header("Idempotency-Key", "conflict-key").contentType("application/json")
                        .content(template.formatted(entity.id(), "Second")))
                .andExpect(status().isConflict());
    }

    @Test
    void kafkaStatusConsumptionIsTransactionalAndDuplicateSafe() throws Exception {
        val body = """
                {"entityId":"%s","request":"Kafka lifecycle","language":"en"}
                """.formatted(entity.id());
        val response = mockMvc.perform(post("/api/executions/report-plans").with(csrf()).with(login())
                        .header("Idempotency-Key", "kafka-key").contentType("application/json")
                        .content(body))
                .andExpect(status().isCreated()).andReturn().getResponse().getContentAsString();
        val executionId = UUID.fromString(mapper.readTree(response).path("id").stringValue());
        val eventId = UUID.randomUUID();
        val event = mapper.createObjectNode()
                .put("schemaVersion", "1.0").put("eventId", eventId.toString())
                .put("correlationId", "kafka-integration")
                .put("executionId", executionId.toString())
                .put("entityId", entity.id().toString())
                .put("actorUserId", reporter.getId().toString())
                .put("occurredAt", Instant.now().toString())
                .put("stage", "QUEUED").put("status", "QUEUED")
                .put("progressPercent", 0).put("messageCode", "EXECUTION_QUEUED");
        event.putObject("details").put("source", "integration-test");
        val payload = messageSigner.wrap(mapper.writeValueAsString(event));
        kafka.send("execution.events.v1", executionId.toString(), payload).get();
        kafka.send("execution.events.v1", executionId.toString(), payload).get();
        org.awaitility.Awaitility.await().atMost(java.time.Duration.ofSeconds(10)).untilAsserted(() ->
                assertThat(jdbc.queryForObject(
                        "select count(*) from execution_status_history where event_id=?",
                        Long.class, eventId)).isEqualTo(1L));
        assertThat(jdbc.queryForObject(
                "select status from execution_request where id=?", String.class, executionId))
                .isEqualTo("QUEUED");
        mockMvc.perform(get("/api/executions/{id}", executionId).with(login()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("QUEUED"))
                .andExpect(jsonPath("$.history[1].eventId").value(eventId.toString()));
        mockMvc.perform(get("/api/executions/{id}/stream", executionId).with(login()))
                .andExpect(status().isOk())
                .andExpect(request().asyncStarted());
    }

    @Test
    void persistsSanitizedFailureAndExposesHumanExplanation() throws Exception {
        val body = """
                {"entityId":"%s","request":"Recent sales","language":"en"}
                """.formatted(entity.id());
        val response = mockMvc.perform(post("/api/executions/report-plans").with(csrf()).with(login())
                        .header("Idempotency-Key", "failure-key").contentType("application/json")
                        .content(body))
                .andExpect(status().isCreated()).andReturn().getResponse().getContentAsString();
        val executionId = UUID.fromString(mapper.readTree(response).path("id").stringValue());
        val event = mapper.createObjectNode()
                .put("schemaVersion", "1.0").put("eventId", UUID.randomUUID().toString())
                .put("correlationId", "failure-integration")
                .put("executionId", executionId.toString())
                .put("entityId", entity.id().toString())
                .put("actorUserId", reporter.getId().toString())
                .put("occurredAt", Instant.now().toString())
                .put("stage", "FAILED").put("status", "FAILED")
                .put("progressPercent", 100).put("messageCode", "SPARK_JOB_FAILED");
        event.putObject("details")
                .put("schemaVersion", "1.0")
                .put("failureCode", "REPORT_ORDER_SHAPE_INVALID")
                .put("failedStage", "RUNNING")
                .put("technicalReason", "The approved plan mixed row fields and aggregation.")
                .put("userExplanation", "List records without aggregation or group totals.")
                .put("explanationStatus", "COMPLETED")
                .put("retryable", false).put("language", "en");
        kafka.send("execution.events.v1", executionId.toString(),
                messageSigner.wrap(mapper.writeValueAsString(event))).get();

        org.awaitility.Awaitility.await().atMost(Duration.ofSeconds(10)).untilAsserted(() ->
                assertThat(jdbc.queryForObject(
                        "select count(*) from execution_failure where execution_id=?",
                        Long.class, executionId)).isEqualTo(1L));
        mockMvc.perform(get("/api/executions/{id}", executionId).with(login()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("FAILED"))
                .andExpect(jsonPath("$.failure.failureCode")
                        .value("REPORT_ORDER_SHAPE_INVALID"))
                .andExpect(jsonPath("$.failure.sanitizedTechnicalReason")
                        .value("The approved plan mixed row fields and aggregation."))
                .andExpect(jsonPath("$.failure.userExplanation")
                        .value("List records without aggregation or group totals."))
                .andExpect(jsonPath("$.failure.explanationStatus").value("COMPLETED"));
    }

    @Test
    void registersBoundedResultAndArtifactIdempotentlyWithRoleAwareGuidance() throws Exception {
        val body = """
                {"entityId":"%s","request":"Result registration","language":"en"}
                """.formatted(entity.id());
        val response = mockMvc.perform(post("/api/executions/report-plans").with(csrf()).with(login())
                        .header("Idempotency-Key", "result-key").contentType("application/json")
                        .content(body))
                .andExpect(status().isCreated()).andReturn().getResponse().getContentAsString();
        val executionId = UUID.fromString(mapper.readTree(response).path("id").stringValue());
        val eventId = UUID.randomUUID();
        val artifactId = UUID.randomUUID();
        val managementSummary = "Evidence-grounded management explanation. ".repeat(3_000);
        val event = mapper.createObjectNode()
                .put("schemaVersion", "1.0").put("eventId", eventId.toString())
                .put("correlationId", "result-integration")
                .put("executionId", executionId.toString())
                .put("entityId", entity.id().toString())
                .put("actorUserId", reporter.getId().toString())
                .put("occurredAt", Instant.now().toString())
                .put("status", "SUCCEEDED").put("resultCode", "EXECUTION_RESULT_READY")
                .put("rowCount", 123).put("summaryStatus", "COMPLETED")
                .put("managementSummary", managementSummary)
                .put("summaryValidationStatus", "ACCEPTED");
        event.putObject("summaryEvidence")
                .put("schemaVersion", "2.0")
                .put("semanticRegistryVersion", "1.0")
                .put("executionType", "REPORT")
                .put("language", "en")
                .put("containsRawRows", false);
        event.putArray("summaryValidationIssues");
        val audit = event.putObject("summaryAudit").put("schemaVersion", "2.0")
                .put("language", "en")
                .put("prose", "Evidence-grounded management explanation.");
        audit.putArray("evidenceIds").add("result.row-count");
        val scope = audit.putObject("scope");
        scope.putArray("evidenceScopes").add("COMPLETE_RESULT");
        scope.putArray("populationScopes").add("OVERALL");
        scope.putArray("groupingDimensions");
        scope.putArray("groupingValues");
        scope.putArray("periods");
        scope.putArray("aggregations");
        scope.putArray("datasetRoles").add("NONE");
        scope.putArray("scenarioCodes");
        scope.putArray("selectedModels");
        scope.putArray("selectionMetrics");
        scope.putArray("metricCodes");
        scope.putArray("metricAveragingScopes");
        event.putArray("summaryBlockingIssues");
        event.putArray("summaryAdvisoryIssues");
        event.put("summaryRepairAttemptCount", 0);
        event.put("summaryProvider", "deterministic-test");
        event.put("summaryProviderModel", "deterministic-test-model");
        event.put("summaryGeneratedAt", Instant.now().toString());
        event.putObject("preview").putArray("columns");
        event.withObject("preview").putArray("rows");
        event.withObject("preview").put("limit", 100).put("truncated", true);
        event.putArray("kpis");
        event.putArray("charts");
        event.putArray("warnings").addObject().put("code", "RESULT_TRUNCATED")
                .put("messageKey", "result.warning.truncated");
        event.putObject("artifact").put("artifactId", artifactId.toString())
                .put("format", "PARQUET").put("bucket", "results")
                .put("objectKey", "executions/" + executionId + "/result.parquet")
                .put("sizeBytes", 4096);
        val payload = messageSigner.wrap(mapper.writeValueAsString(event));
        kafka.send("execution.results.v1", executionId.toString(), payload).get();
        kafka.send("execution.results.v1", executionId.toString(), payload).get();
        org.awaitility.Awaitility.await().atMost(java.time.Duration.ofSeconds(10)).untilAsserted(() ->
                assertThat(jdbc.queryForObject(
                        "select count(*) from execution_result where execution_id=?",
                        Long.class, executionId)).isEqualTo(1L));
        assertThat(jdbc.queryForObject("select count(*) from execution_artifact where id=?",
                Long.class, artifactId)).isEqualTo(1L);
        assertThat(jdbc.queryForObject("""
                select summary_evidence_json ->> 'schemaVersion'
                  from execution_result where execution_id=?
                """, String.class, executionId)).isEqualTo("2.0");
        assertThat(jdbc.queryForObject("""
                select summary_validation_status
                  from execution_result where execution_id=?
                """, String.class, executionId)).isEqualTo("ACCEPTED");
        assertThat(jdbc.queryForObject("""
                select jsonb_array_length(summary_validation_issues_json)
                  from execution_result where execution_id=?
                """, Integer.class, executionId)).isZero();
        assertThat(jdbc.queryForObject("""
                select summary_audit_json ->> 'schemaVersion'
                  from execution_result where execution_id=?
                """, String.class, executionId)).isEqualTo("2.0");
        assertThat(jdbc.queryForObject("""
                select summary_provider_model
                  from execution_result where execution_id=?
                """, String.class, executionId)).isEqualTo("deterministic-test-model");
        assertThat(jdbc.queryForObject("""
                select char_length(management_summary)
                  from execution_result where execution_id=?
                """, Integer.class, executionId)).isEqualTo(managementSummary.length());
        mockMvc.perform(get("/api/executions/{id}/result", executionId).with(login()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.rowCount").value(123))
                .andExpect(jsonPath("$.preview.truncated").value(true))
                .andExpect(jsonPath("$.artifact.downloadAvailable").doesNotExist())
                .andExpect(jsonPath("$.artifact.jupyterAvailable").doesNotExist())
                .andExpect(jsonPath("$.summaryStatus").value("COMPLETED"))
                .andExpect(jsonPath("$.summaryValidationStatus").value("ACCEPTED"))
                .andExpect(jsonPath("$.guidanceKey")
                        .value("result.guidance.governedPreview"));
        jdbc.update("""
                update execution_result
                   set summary_status='FAILED', management_summary=null,
                       summary_validation_status='PROVIDER_FAILED',
                       summary_validation_issues_json='["SUMMARY_PROVIDER_FAILED"]'::jsonb,
                       summary_blocking_issues_json='["SUMMARY_PROVIDER_FAILED"]'::jsonb,
                       summary_advisory_issues_json='[]'::jsonb
                 where execution_id=?
                """, executionId);
        mockMvc.perform(get("/api/executions/{id}/result", executionId).with(login()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.rowCount").value(123))
                .andExpect(jsonPath("$.artifact.artifactId").value(artifactId.toString()))
                .andExpect(jsonPath("$.summaryStatus").value("FAILED"))
                .andExpect(jsonPath("$.summaryValidationStatus").value("PROVIDER_FAILED"))
                .andExpect(jsonPath("$.managementSummary").doesNotExist());
    }

    @Test
    void reporterCannotPlanMlWhileScientistCreatesImmutableMlExecution() throws Exception {
        val body = """
                {"entityId":"%s","request":"Predict amount","language":"en"}
                """.formatted(entity.id());
        mockMvc.perform(post("/api/executions/ml-plans").with(csrf()).with(login())
                        .header("Idempotency-Key", "ml-reporter").contentType("application/json")
                        .content(body))
                .andExpect(status().isForbidden());
        val response = mockMvc.perform(post("/api/executions/ml-plans").with(csrf())
                        .with(oidcLogin().idToken(token ->
                                token.subject(reporter.getKeycloakUserId()))
                                .authorities(new SimpleGrantedAuthority(
                                        PlatformRole.SCIENTIST.authority())))
                        .header("Idempotency-Key", "ml-scientist")
                        .contentType("application/json").content(body))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.executionType").value("ML"))
                .andExpect(jsonPath("$.order.algorithm").doesNotExist())
                .andExpect(jsonPath("$.order.payload.algorithm").value("LINEAR_REGRESSION"))
                .andReturn().getResponse().getContentAsString();
        val executionId = UUID.fromString(mapper.readTree(response).path("id").stringValue());
        assertThat(jdbc.queryForObject(
                "select execution_type from execution_request where id=?",
                String.class, executionId)).isEqualTo("ML");
        assertThat(jdbc.queryForObject(
                "select message_code from execution_status_history where execution_id=?",
                String.class, executionId)).isEqualTo("ML_ORDER_VALIDATED");
    }

    @Test
    void cancellationIsOwnedIdempotentAuditedAndPublished() throws Exception {
        val body = """
                {"entityId":"%s","request":"Cancelable report","language":"en"}
                """.formatted(entity.id());
        val response = mockMvc.perform(post("/api/executions/report-plans").with(csrf()).with(login())
                        .header("Idempotency-Key", "cancel-key").contentType("application/json")
                        .content(body))
                .andExpect(status().isCreated()).andReturn().getResponse().getContentAsString();
        val executionId = UUID.fromString(mapper.readTree(response).path("id").stringValue());

        mockMvc.perform(post("/api/executions/{id}/cancel", executionId)
                        .with(csrf()).with(login()))
                .andExpect(status().isAccepted());
        mockMvc.perform(post("/api/executions/{id}/cancel", executionId)
                        .with(csrf()).with(login()))
                .andExpect(status().isAccepted());

        assertThat(jdbc.queryForObject("""
                select count(*) from execution_status_history
                where execution_id=? and stage='CANCELLATION_REQUESTED'
                """, Long.class, executionId)).isEqualTo(1L);
        assertThat(jdbc.queryForObject("""
                select count(*) from audit_event
                where subject_id=? and event_type='EXECUTION_CANCELLATION_REQUESTED'
                """, Long.class, executionId.toString())).isEqualTo(1L);

        mockMvc.perform(post("/api/executions/{id}/cancel", UUID.randomUUID())
                        .with(csrf()).with(login()))
                .andExpect(status().isNotFound());
    }

    private org.springframework.test.web.servlet.request.RequestPostProcessor login() {
        return oidcLogin().idToken(token -> token.subject(reporter.getKeycloakUserId()))
                .authorities(new SimpleGrantedAuthority(PlatformRole.REPORTER.authority()));
    }
}
