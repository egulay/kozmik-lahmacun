package io.gulay.integration;

import lombok.val;

import io.gulay.chat.client.PythonChatClient;
import io.gulay.chat.client.PythonChatContracts;
import io.gulay.chat.data.model.ChatMessageStatus;
import io.gulay.chat.data.repository.ChatMessageRepository;
import io.gulay.chat.data.repository.ChatThreadRepository;
import io.gulay.chat.data.service.ChatService;
import io.gulay.chat.dto.ChatDtos;
import io.gulay.security.PlatformRole;
import io.gulay.user.data.model.AppUserReferenceModel;
import io.gulay.user.data.repository.AppUserReferenceRepository;
import java.time.Duration;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
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
import static org.awaitility.Awaitility.await;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import tools.jackson.databind.ObjectMapper;

@SpringBootTest
@AutoConfigureMockMvc
@Testcontainers
class ChatIntegrationTest {
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
                () -> "test-secret");
        registry.add("server.servlet.session.cookie.secure", () -> "false");
    }

    @Autowired MockMvc mockMvc;
    @Autowired ObjectMapper objectMapper;
    @Autowired AppUserReferenceRepository users;
    @Autowired ChatMessageRepository messages;
    @Autowired ChatThreadRepository threads;
    @Autowired ChatService chatService;
    @MockitoBean PythonChatClient pythonClient;
    @MockitoBean org.springframework.security.oauth2.jwt.JwtDecoder jwtDecoder;
    @MockitoBean org.springframework.security.oauth2.client.registration.ClientRegistrationRepository
            clientRegistrationRepository;

    AppUserReferenceModel owner;
    AppUserReferenceModel other;

    @BeforeEach
    void setUp() {
        owner = user("chat-owner-" + UUID.randomUUID());
        other = user("chat-other-" + UUID.randomUUID());
        when(pythonClient.classify(any())).thenAnswer(invocation -> {
            val request = (PythonChatContracts.ClassificationRequest) invocation.getArgument(0);
            return new PythonChatContracts.ClassificationResponse(
                    "1.0", request.requestId(), request.correlationId(),
                    "CONVERSATIONAL", null, "mock", "mock-v1");
        });
    }

    @Test
    void listsOwnedThreadsWithDeterministicServerSidePaging() throws Exception {
        for (var index = 0; index < 7; index++) {
            chatService.createThread(owner.getKeycloakUserId(),
                    new ChatDtos.CreateThreadRequest("Thread " + index, "en"));
        }
        chatService.createThread(other.getKeycloakUserId(),
                new ChatDtos.CreateThreadRequest("Other user's thread", "en"));

        val first = objectMapper.readTree(mockMvc.perform(get("/api/chat/threads")
                        .param("page", "0").param("size", "5").with(login(owner)))
                .andExpect(status().isOk()).andReturn().getResponse().getContentAsString());
        val second = objectMapper.readTree(mockMvc.perform(get("/api/chat/threads")
                        .param("page", "1").param("size", "5").with(login(owner)))
                .andExpect(status().isOk()).andReturn().getResponse().getContentAsString());

        assertThat(first.get("threads").size()).isEqualTo(5);
        assertThat(first.get("totalElements").asLong()).isEqualTo(7);
        assertThat(first.get("totalPages").asInt()).isEqualTo(2);
        assertThat(first.get("first").asBoolean()).isTrue();
        assertThat(first.get("last").asBoolean()).isFalse();
        assertThat(second.get("threads").size()).isEqualTo(2);
        assertThat(second.get("last").asBoolean()).isTrue();
        assertThat(first.toString()).doesNotContain("Other user's thread");
        assertThat(second.toString()).doesNotContain("Other user's thread");
    }

    @Test
    void usesCurrentUiLanguageForEachPostedMessage() {
        val thread = chatService.createThread(owner.getKeycloakUserId(),
                new ChatDtos.CreateThreadRequest("Language switch", "en"));

        val posted = chatService.post(thread.id(), owner.getKeycloakUserId(),
                new ChatDtos.PostMessageRequest("Satışları analiz et", "tr"));

        assertThat(posted.streamRequest().language()).isEqualTo("tr");
    }

    @Test
    void persistsCompletionAndProvidesReconnectSafeSseTerminalEvent() throws Exception {
        doAnswer(invocation -> {
            val request = (PythonChatContracts.StreamRequest) invocation.getArgument(0);
            @SuppressWarnings("unchecked")
            java.util.function.Consumer<PythonChatContracts.StreamEvent> consumer =
                    invocation.getArgument(1);
            consumer.accept(event(request, "message-started", null, null));
            consumer.accept(event(request, "message-delta", "hello ", null));
            consumer.accept(event(request, "message-completed", null, "hello world"));
            return null;
        }).when(pythonClient).stream(any(), any());

        val threadId = createThread(owner);
        val posted = postMessage(threadId, owner, "question");
        val assistantId = UUID.fromString(posted.get("assistantMessage").get("id").stringValue());

        await().atMost(Duration.ofSeconds(5)).untilAsserted(() ->
                assertThat(messages.findById(assistantId).orElseThrow().getStatus())
                        .isEqualTo(ChatMessageStatus.COMPLETED));
        val result = mockMvc.perform(get("/api/chat/threads/{id}/stream", threadId)
                        .param("assistantMessageId", assistantId.toString())
                        .with(login(owner)))
                .andExpect(status().isOk())
                .andExpect(request().asyncStarted())
                .andReturn();
        result.getAsyncResult(2_000);
        mockMvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders
                        .asyncDispatch(result))
                .andExpect(status().isOk())
                .andExpect(content -> assertThat(content.getResponse().getContentAsString())
                        .contains("event:message-completed", "hello world"));
    }

    @Test
    void persistsSanitizedFailureAndStreamsFailureOnReconnect() throws Exception {
        doAnswer(invocation -> {
            val request = (PythonChatContracts.StreamRequest) invocation.getArgument(0);
            @SuppressWarnings("unchecked")
            java.util.function.Consumer<PythonChatContracts.StreamEvent> consumer =
                    invocation.getArgument(1);
            consumer.accept(event(request, "message-started", null, null));
            consumer.accept(new PythonChatContracts.StreamEvent(
                    "1.0", UUID.randomUUID(), request.correlationId(),
                    request.assistantMessageId(), "message-failed", null, null,
                    "mock", "mock-v1", "PROVIDER_TIMEOUT"));
            return null;
        }).when(pythonClient).stream(any(), any());

        val threadId = createThread(owner);
        val posted = postMessage(threadId, owner, "fail");
        val assistantId = UUID.fromString(posted.get("assistantMessage").get("id").stringValue());

        await().atMost(Duration.ofSeconds(5)).untilAsserted(() -> {
            val failed = messages.findById(assistantId).orElseThrow();
            assertThat(failed.getStatus()).isEqualTo(ChatMessageStatus.FAILED);
            assertThat(failed.getErrorCode()).isEqualTo("PROVIDER_TIMEOUT");
            assertThat(failed.getContent()).isEmpty();
        });
        val result = mockMvc.perform(get("/api/chat/threads/{id}/stream", threadId)
                        .param("assistantMessageId", assistantId.toString())
                        .with(login(owner)))
                .andExpect(request().asyncStarted()).andReturn();
        result.getAsyncResult(2_000);
        mockMvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders
                        .asyncDispatch(result))
                .andExpect(content -> assertThat(content.getResponse().getContentAsString())
                        .contains("event:message-failed", "PROVIDER_TIMEOUT"));
    }

    @Test
    void enforcesThreadOwnershipForRestAndSse() throws Exception {
        val threadId = createThread(owner);

        mockMvc.perform(get("/api/chat/threads/{id}/messages", threadId).with(login(other)))
                .andExpect(status().isNotFound());
        mockMvc.perform(get("/api/chat/threads/{id}/stream", threadId)
                        .param("assistantMessageId", UUID.randomUUID().toString())
                        .with(login(other)))
                .andExpect(status().isNotFound());
    }

    @Test
    void ownerCanSoftDeleteThreadAndAnotherUserCannotDeleteIt() throws Exception {
        val threadId = createThread(owner);
        postMessage(threadId, owner, "private conversation");

        mockMvc.perform(delete("/api/chat/threads/{id}", threadId)
                        .with(csrf()).with(login(other)))
                .andExpect(status().isNotFound());

        mockMvc.perform(delete("/api/chat/threads/{id}", threadId)
                        .with(csrf()).with(login(owner)))
                .andExpect(status().isNoContent());

        mockMvc.perform(get("/api/chat/threads/{id}/messages", threadId).with(login(owner)))
                .andExpect(status().isNotFound());
        assertThat(threads.findById(threadId)).isEmpty();
        assertThat(messages.findAll().stream()
                .filter(message -> message.getThread().getId().equals(threadId))).isEmpty();
    }

    @Test
    void constructsBoundedHistory() {
        val thread = chatService.createThread(owner.getKeycloakUserId(),
                new ChatDtos.CreateThreadRequest("Bounded", "en"));
        ChatService.PostedMessages last = null;
        for (var index = 0; index < 12; index++) {
            last = chatService.post(thread.id(), owner.getKeycloakUserId(),
                    new ChatDtos.PostMessageRequest("message-" + index, "en"));
            chatService.complete(last.response().assistantMessage().id(),
                    "answer-" + index, "mock", "mock-v1");
        }

        assertThat(last).isNotNull();
        assertThat(last.streamRequest().history()).hasSize(20);
        assertThat(last.streamRequest().history().get(0).content()).isEqualTo("answer-1");
        assertThat(last.streamRequest().history().get(19).content()).isEqualTo("message-11");
    }

    private UUID createThread(AppUserReferenceModel user) throws Exception {
        val response = mockMvc.perform(post("/api/chat/threads")
                        .with(csrf()).with(login(user)).contentType("application/json")
                        .content("{\"title\":\"Test thread\",\"language\":\"en\"}"))
                .andExpect(status().isCreated()).andReturn().getResponse().getContentAsString();
        return UUID.fromString(objectMapper.readTree(response).get("id").stringValue());
    }

    private tools.jackson.databind.JsonNode postMessage(
            UUID threadId, AppUserReferenceModel user, String content) throws Exception {
        val response = mockMvc.perform(post("/api/chat/threads/{id}/messages", threadId)
                        .with(csrf()).with(login(user)).contentType("application/json")
                        .content(objectMapper.writeValueAsString(
                                new ChatDtos.PostMessageRequest(content, "en"))))
                .andExpect(status().isAccepted()).andReturn().getResponse().getContentAsString();
        return objectMapper.readTree(response);
    }

    private PythonChatContracts.StreamEvent event(
            PythonChatContracts.StreamRequest request, String type, String delta, String content) {
        return new PythonChatContracts.StreamEvent(
                "1.0", UUID.randomUUID(), request.correlationId(),
                request.assistantMessageId(), type, delta, content, "mock", "mock-v1", null);
    }

    private org.springframework.test.web.servlet.request.RequestPostProcessor login(
            AppUserReferenceModel user) {
        return oidcLogin().idToken(token -> token.subject(user.getKeycloakUserId()))
                .authorities(new SimpleGrantedAuthority(PlatformRole.REPORTER.authority()));
    }

    private AppUserReferenceModel user(String keycloakId) {
        val now = Instant.now();
        return users.save(AppUserReferenceModel.builder().id(UUID.randomUUID())
                .keycloakUserId(keycloakId).displayName(keycloakId)
                .createdAt(now).updatedAt(now).build());
    }
}
