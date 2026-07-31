package io.gulay.integration;

import lombok.val;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import io.gulay.api.ConflictException;
import io.gulay.entity.data.model.ColumnDataType;
import io.gulay.entity.data.service.EntityManagementService;
import io.gulay.entity.dto.EntityDtos;
import io.gulay.security.PlatformRole;
import io.gulay.user.data.model.AppUserReferenceModel;
import io.gulay.user.data.repository.AppUserReferenceRepository;
import java.time.Instant;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.DockerImageName;

@SpringBootTest
@Testcontainers
class EntityManagementIntegrationTest {
    @Container static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer(DockerImageName.parse("postgres:16.4-alpine3.20"))
                    .withDatabaseName("kozmik").withUsername("kozmik")
                    .withPassword("integration-password");
    @Container static final GenericContainer<?> REDIS =
            new GenericContainer<>(DockerImageName.parse("redis:7.2.5-alpine3.20"))
                    .withExposedPorts(6379);

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRES::getUsername);
        registry.add("spring.datasource.password", POSTGRES::getPassword);
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add("spring.data.redis.port", () -> REDIS.getMappedPort(6379));
        registry.add("spring.data.redis.password", () -> "");
        registry.add("spring.security.oauth2.client.registration.keycloak.client-secret",
                () -> "integration-client-secret");
        registry.add("kozmik.security.internal-api-key", () -> "integration-internal-key");
        registry.add("kozmik.ingestion.system-keycloak-user-id",
                () -> "integration-ingestion-system");
        registry.add("spring.kafka.listener.auto-startup", () -> "false");
        registry.add("kozmik.kafka.outbox-enabled", () -> "false");
    }

    @Autowired EntityManagementService service;
    @Autowired AppUserReferenceRepository users;
    @MockitoBean org.springframework.security.oauth2.jwt.JwtDecoder jwtDecoder;
    @MockitoBean org.springframework.security.oauth2.client.registration.ClientRegistrationRepository
            clientRegistrationRepository;

    private AppUserReferenceModel reporter;

    @BeforeEach
    void setup() {
        ensureUser("integration-ingestion-system");
        reporter = ensureUser("reporter-" + UUID.randomUUID());
    }

    @Test
    void entityUuidOwnsOneImmutableStructureVisibleToEveryAuthenticatedUser() {
        val descriptor = descriptor(UUID.randomUUID(), ColumnDataType.DECIMAL);
        val schema = service.resolveOrRegisterStreamEntity(descriptor);

        assertThat(schema.entityId()).isEqualTo(descriptor.id());
        assertThat(schema.columns()).extracting(EntityDtos.ColumnDefinition::columnName)
                .containsExactly("amount");
        assertThat(service.currentSchema(
                descriptor.id(), reporter.getKeycloakUserId(), Set.of(PlatformRole.REPORTER)))
                .isEqualTo(schema);
    }

    @Test
    void sameUuidWithChangedStructureIsRejected() {
        val id = UUID.randomUUID();
        service.resolveOrRegisterStreamEntity(descriptor(id, ColumnDataType.DECIMAL));

        assertThatThrownBy(() ->
                service.resolveOrRegisterStreamEntity(descriptor(id, ColumnDataType.STRING)))
                .isInstanceOf(ConflictException.class)
                .hasMessageContaining("different structure");
    }

    @Test
    void returnsIngestionMetadataInRequestedDisplayLanguage() {
        val id = UUID.randomUUID();
        val descriptor = new EntityDtos.StreamEntityDescriptor(
                id, "Sales Transactions", "Sales transaction data",
                List.of(new EntityDtos.ColumnDefinition(
                        null, "net_amount", "Net amount", ColumnDataType.DECIMAL,
                        "Net sales amount", 1, "Net tutar", "Net satış tutarı")),
                "Satış İşlemleri", "Satış işlem verileri");
        service.resolveOrRegisterStreamEntity(descriptor);

        val turkishEntity = service.get(
                id, reporter.getKeycloakUserId(), Set.of(PlatformRole.REPORTER), "tr");
        val turkishSchema = service.currentSchema(
                id, reporter.getKeycloakUserId(), Set.of(PlatformRole.REPORTER), "tr");

        assertThat(turkishEntity.name()).isEqualTo("Satış İşlemleri");
        assertThat(turkishEntity.description()).isEqualTo("Satış işlem verileri");
        assertThat(turkishSchema.columns().get(0).businessName()).isEqualTo("Net tutar");
    }

    @Test
    void persistsBoundedCategoricalVocabularyAsColumnMetadata() {
        val id = UUID.randomUUID();
        val descriptor = new EntityDtos.StreamEntityDescriptor(
                id, "Orders-" + id, "Order data",
                List.of(new EntityDtos.ColumnDefinition(
                        null, "channel", "Channel", ColumnDataType.STRING,
                        "Sales channel", 1, null, null,
                        List.of("WEB", "STORE", "PARTNER"))));

        service.resolveOrRegisterStreamEntity(descriptor);
        val schema = service.internalIngestionSchema(id);

        assertThat(schema.columns().get(0).categoricalValues())
                .containsExactly("PARTNER", "STORE", "WEB");
    }

    private EntityDtos.StreamEntityDescriptor descriptor(
            UUID id, ColumnDataType type) {
        return new EntityDtos.StreamEntityDescriptor(
                id, "Entity-" + id, "Discovered structure",
                List.of(new EntityDtos.ColumnDefinition(
                        null, "amount", "Amount", type, "Observed column", 1)));
    }

    private AppUserReferenceModel ensureUser(String keycloakId) {
        val now = Instant.now();
        return users.findByKeycloakUserId(keycloakId).orElseGet(() ->
                users.save(AppUserReferenceModel.builder().id(UUID.randomUUID())
                        .keycloakUserId(keycloakId).createdAt(now).updatedAt(now).build()));
    }
}
