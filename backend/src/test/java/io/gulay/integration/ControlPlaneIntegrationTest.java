package io.gulay.integration;

import lombok.val;

import io.gulay.security.PlatformRole;
import io.gulay.user.data.repository.AppUserReferenceRepository;
import io.gulay.user.data.service.AppUserReferenceService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.web.HttpSessionOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;
import org.springframework.session.data.redis.RedisIndexedSessionRepository;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.DockerImageName;
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Testcontainers
class ControlPlaneIntegrationTest {
    @MockitoBean org.springframework.security.oauth2.jwt.JwtDecoder jwtDecoder;
    @MockitoBean org.springframework.security.oauth2.client.registration.ClientRegistrationRepository
            clientRegistrationRepository;

    @Container
    static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer(DockerImageName.parse("postgres:16.4-alpine3.20"))
                    .withDatabaseName("kozmik")
                    .withUsername("kozmik")
                    .withPassword("integration-password");

    @Container
    static final GenericContainer<?> REDIS =
            new GenericContainer<>(DockerImageName.parse("redis:7.2.5-alpine3.20"))
                    .withExposedPorts(6379);

    @DynamicPropertySource
    static void infrastructureProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRES::getUsername);
        registry.add("spring.datasource.password", POSTGRES::getPassword);
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add("spring.data.redis.port", () -> REDIS.getMappedPort(6379));
        registry.add("spring.data.redis.password", () -> "");
        registry.add("spring.security.oauth2.client.registration.keycloak.client-secret",
                () -> "integration-client-secret");
        registry.add("kozmik.security.internal-api-key", () -> "integration-internal-key");
        registry.add("server.servlet.session.cookie.secure", () -> "false");
    }

    @Autowired
    MockMvc mockMvc;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Autowired
    AppUserReferenceService userService;

    @Autowired
    AppUserReferenceRepository userRepository;

    @Autowired
    RedisIndexedSessionRepository sessionRepository;

    @Autowired
    OAuth2AuthorizedClientRepository authorizedClientRepository;

    @Test
    void flywayCreatesFoundationAndEntitySchemaTables() {
        val tables = jdbcTemplate.queryForList(
                """
                SELECT table_name
                  FROM information_schema.tables
                 WHERE table_schema = 'kozmik_lahmacun'
                """,
                String.class);

        assertThat(tables)
                .contains(
                        "app_user_reference",
                        "audit_event",
                        "business_entity",
                        "entity_column",
                        "chat_thread",
                        "chat_message",
                        "execution_request",
                        "execution_status_history",
                        "execution_command_outbox",
                        "processed_execution_event",
                        "execution_result",
                        "execution_artifact",
                        "import_job",
                        "import_status_history")
                .doesNotContain("artifact", "platform_setting", "executor_restart_command");
    }

    @Test
    void synchronizesKeycloakReferenceWithoutCreatingIdentityCredentials() {
        userService.synchronize(
                "keycloak-user-1", "Initial Name", "initial@example.test");
        userService.synchronize(
                "keycloak-user-1", "Updated Name", "updated@example.test");

        assertThat(userRepository.findAll()).singleElement().satisfies(user -> {
            assertThat(user.getKeycloakUserId()).isEqualTo("keycloak-user-1");
            assertThat(user.getDisplayName()).isEqualTo("Updated Name");
            assertThat(user.getEmail()).isEqualTo("updated@example.test");
        });
    }

    @Test
    void redisStoresOpaqueServerSideSessionState() {
        assertThat(authorizedClientRepository)
                .isInstanceOf(HttpSessionOAuth2AuthorizedClientRepository.class);
        val session = sessionRepository.createSession();
        session.setAttribute("keycloakAuthorizedClientReference", "server-side-only");
        sessionRepository.save(session);

        val restored = sessionRepository.findById(session.getId());
        assertThat(restored).isNotNull();
        assertThat((String) restored.getAttribute("keycloakAuthorizedClientReference"))
                .isEqualTo("server-side-only");
        assertThat(session.getId()).doesNotContain("server-side-only");
    }

    @Test
    void unauthenticatedApiRequestReturnsUnauthorizedInsteadOfRedirect() throws Exception {
        mockMvc.perform(get("/api/auth/me")).andExpect(status().isUnauthorized());
    }

    @Test
    void currentUserReturnsOnlyAuthenticatedIdentityAndPlatformRoles() throws Exception {
        mockMvc.perform(get("/api/auth/me")
                        .with(oidcLogin()
                                .idToken(token -> token
                                        .subject("keycloak-user-2")
                                        .claim("preferred_username", "ada")
                                        .claim("name", "Ada Lovelace")
                                        .claim("email", "ada@example.test"))
                                .authorities(
                                        new SimpleGrantedAuthority("ROLE_REPORTER"),
                                        new SimpleGrantedAuthority("OIDC_USER"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.userId").value("keycloak-user-2"))
                .andExpect(jsonPath("$.username").value("ada"))
                .andExpect(jsonPath("$.displayName").value("Ada Lovelace"))
                .andExpect(jsonPath("$.email").value("ada@example.test"))
                .andExpect(jsonPath("$.roles[0]").value("REPORTER"));
    }

    @Test
    void currentUserDoesNotExposeKeycloakCompositeRoleExpansion() throws Exception {
        mockMvc.perform(get("/api/auth/me")
                        .with(oidcLogin()
                                .idToken(token -> token
                                        .subject("keycloak-admin")
                                        .claim("preferred_username", "admin")
                                        .claim("name", "Demo User")
                                        .claim("email", "admin@example.test"))
                                .authorities(
                                        new SimpleGrantedAuthority("ROLE_ADMIN"),
                                        new SimpleGrantedAuthority("ROLE_SCIENTIST"),
                                        new SimpleGrantedAuthority("ROLE_REPORTER"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.roles.length()").value(1))
                .andExpect(jsonPath("$.roles[0]").value("ADMIN"));
    }

    @Test
    void browserReceivesCsrfTokenAndMutationsRejectMissingToken() throws Exception {
        val admin = oidcLogin().authorities(
                new SimpleGrantedAuthority(PlatformRole.ADMIN.authority()));

        mockMvc.perform(get("/api/auth/csrf").with(admin))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.headerName").value("X-CSRF-TOKEN"))
                .andExpect(jsonPath("$.parameterName").value("_csrf"))
                .andExpect(jsonPath("$.token").isNotEmpty());

        mockMvc.perform(post("/api/admin/users/{id}/suspend", java.util.UUID.randomUUID())
                        .with(admin))
                .andExpect(status().isForbidden());
    }

    @Test
    void actuatorInformationRequiresAdminRole() throws Exception {
        mockMvc.perform(get("/actuator/info")
                        .with(oidcLogin().authorities(
                                new SimpleGrantedAuthority(PlatformRole.REPORTER.authority()))))
                .andExpect(status().isForbidden());

        mockMvc.perform(get("/actuator/info")
                        .with(oidcLogin().authorities(
                                new SimpleGrantedAuthority(PlatformRole.ADMIN.authority()))))
                .andExpect(status().isOk());
    }

    @Test
    void pythonEffectiveConfigurationIsInternalAndContainsNoSecret() throws Exception {
        mockMvc.perform(get("/internal/v1/config/effective"))
                .andExpect(status().isUnauthorized());

        val body = mockMvc.perform(get("/internal/v1/config/effective")
                        .header("X-Internal-API-Key", "integration-internal-key"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.schemaVersion").value("1.0"))
                .andExpect(jsonPath("$.llm.provider").value("LM_STUDIO"))
                .andExpect(jsonPath("$.llm.timeoutSeconds").value(60))
                .andReturn().getResponse().getContentAsString();

        assertThat(body)
                .doesNotContainIgnoringCase("secret")
                .doesNotContainIgnoringCase("apiKey")
                .doesNotContain("integration-client-secret");
    }
}
