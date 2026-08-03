package io.gulay.chat.controller;

import lombok.val;

import io.gulay.chat.client.PythonChatContracts;
import io.gulay.chat.data.model.ChatMessageStatus;
import io.gulay.chat.data.service.ChatService;
import io.gulay.chat.data.service.ChatStreamCoordinator;
import io.gulay.chat.data.service.ChatStreamHub;
import io.gulay.chat.dto.ChatDtos;
import io.gulay.security.PlatformRole;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;

import java.net.URI;
import java.util.Objects;
import java.util.UUID;
import java.util.Set;
import java.util.stream.Collectors;

import lombok.RequiredArgsConstructor;
import org.slf4j.MDC;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@RestController
@RequestMapping("/api/chat/threads")
@RequiredArgsConstructor
public class ChatController {
    private final ChatService chatService;
    private final ChatStreamCoordinator coordinator;
    private final ChatStreamHub hub;

    @PostMapping
    ResponseEntity<ChatDtos.ThreadResponse> create(
            @AuthenticationPrincipal OidcUser user,
            @Valid @RequestBody ChatDtos.CreateThreadRequest request) {
        val created = chatService.createThread(user.getSubject(), request);
        return ResponseEntity.created(URI.create("/api/chat/threads/" + created.id())).body(created);
    }

    @GetMapping
    ChatDtos.ThreadListResponse list(
            @AuthenticationPrincipal OidcUser user,
            @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size) {
        return chatService.listThreads(user.getSubject(), page, size);
    }

    @GetMapping("/{threadId}/messages")
    ChatDtos.MessageListResponse messages(
            @PathVariable UUID threadId,
            @AuthenticationPrincipal OidcUser user,
            @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size) {
        return chatService.messages(threadId, user.getSubject(), page, size);
    }

    @DeleteMapping("/{threadId}")
    ResponseEntity<Void> delete(
            @PathVariable UUID threadId, @AuthenticationPrincipal OidcUser user) {
        chatService.deleteThread(threadId, user.getSubject());
        return ResponseEntity.noContent().build();
    }

    @PutMapping("/{threadId}")
    ChatDtos.ThreadResponse rename(
            @PathVariable UUID threadId,
            @AuthenticationPrincipal OidcUser user,
            @Valid @RequestBody ChatDtos.RenameThreadRequest request) {
        return chatService.renameThread(threadId, user.getSubject(), request);
    }

    @PostMapping("/{threadId}/messages")
    ResponseEntity<ChatDtos.PostedMessageResponse> post(
            @PathVariable UUID threadId,
            @AuthenticationPrincipal OidcUser user,
            Authentication authentication,
            @Valid @RequestBody ChatDtos.PostMessageRequest request) {
        val posted = chatService.post(threadId, user.getSubject(), request);
        val original = posted.streamRequest();
        val roles = roles(authentication);
        val streamRequest = new PythonChatContracts.StreamRequest(
                original.schemaVersion(), original.requestId(), original.threadId(),
                original.assistantMessageId(), original.actorUserId(),
                MDC.get("correlationId"), original.language(),
                roles.stream().map(PlatformRole::name).sorted().toList(),
                original.history());
        coordinator.start(streamRequest, user.getSubject(), roles, request.content());
        return ResponseEntity.accepted().body(posted.response());
    }

    @GetMapping(value = "/{threadId}/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    SseEmitter stream(
            @PathVariable UUID threadId,
            @RequestParam UUID assistantMessageId,
            @RequestHeader(value = "Last-Event-ID", required = false) String lastEventId,
            @AuthenticationPrincipal OidcUser user) {
        val message = chatService.terminalOrCurrent(
                threadId, assistantMessageId, user.getSubject());
        if (message.getStatus() == ChatMessageStatus.COMPLETED
                || message.getStatus() == ChatMessageStatus.FAILED) {
            val name = message.getStatus() == ChatMessageStatus.COMPLETED
                    ? "message-completed" : "message-failed";
            return hub.terminal(assistantMessageId, message.getId() + ":terminal",
                    name, chatService.response(message));
        }
        return hub.subscribe(assistantMessageId, lastEventId);
    }

    private Set<PlatformRole> roles(Authentication authentication) {
        return authentication.getAuthorities().stream()
                .map(org.springframework.security.core.GrantedAuthority::getAuthority)
                .filter(Objects::nonNull)
                .map(authority -> authority.replaceFirst("^ROLE_", ""))
                .map(PlatformRole::fromKeycloakRole)
                .flatMap(java.util.Optional::stream)
                .collect(Collectors.toSet());
    }
}
