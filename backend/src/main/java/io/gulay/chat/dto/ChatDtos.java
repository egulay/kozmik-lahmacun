package io.gulay.chat.dto;

import io.gulay.chat.data.model.ChatMessageStatus;
import io.gulay.chat.data.model.ChatRole;
import io.gulay.chat.data.model.ChatThreadStatus;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

public final class ChatDtos {
    public static final String VERSION = "1.0";

    private ChatDtos() {
    }

    public record CreateThreadRequest(
            @NotBlank @Size(max = 50) String title,
            @NotBlank @Pattern(regexp = "[a-z]{2}(-[A-Z]{2})?") String language) {
    }

    public record RenameThreadRequest(@NotBlank @Size(max = 50) String title) {
    }

    public record PostMessageRequest(
            @NotBlank @Size(max = 20000) String content,
            @NotBlank @Pattern(regexp = "[a-z]{2}(-[A-Z]{2})?") String language) {
    }

    public record ThreadResponse(String schemaVersion, UUID id, String title, String language,
                                 ChatThreadStatus status, Instant createdAt, Instant updatedAt) {
    }

    public record ThreadListResponse(
            String schemaVersion, List<ThreadResponse> threads,
            int page, int size, long totalElements, int totalPages,
            boolean first, boolean last) {
    }

    public record MessageResponse(String schemaVersion, UUID id, UUID threadId, long sequenceNumber,
                                  ChatRole role, String content, String provider, String model,
                                  ChatMessageStatus status,
                                  String errorCode, Instant createdAt, Instant completedAt) {
    }

    public record MessageListResponse(
            String schemaVersion, List<MessageResponse> messages,
            int page, int size, long totalElements, int totalPages,
            boolean first, boolean last) {
    }

    public record PostedMessageResponse(
            String schemaVersion, MessageResponse userMessage, MessageResponse assistantMessage) {
    }
}
