package io.gulay.chat.client;

import java.util.List;
import java.util.UUID;

public final class PythonChatContracts {
    private PythonChatContracts() {
    }

    public record HistoryMessage(String role, String content) {
    }

    public record StreamRequest(String schemaVersion, UUID requestId, UUID threadId,
                                UUID assistantMessageId, UUID actorUserId, String correlationId, String language,
                                List<String> capabilities, List<HistoryMessage> history) {
    }

    public record StreamEvent(String schemaVersion, UUID eventId, String correlationId,
                              UUID assistantMessageId, String type, String delta, String content,
                              String provider, String model, String errorCode) {
    }

    public record EntityMetadata(
            UUID entityId, String name, String description, List<String> columnNames,
            List<String> columnLabels) {
    }

    public record ClassificationRequest(String schemaVersion, UUID requestId,
                                        String correlationId, UUID actorUserId, String language,
                                        List<String> capabilities, String userRequest, List<HistoryMessage> history,
                                        List<EntityMetadata> entities) {
    }

    public record ClassificationResponse(String schemaVersion, UUID requestId,
                                         String correlationId, String intent, UUID selectedEntityId,
                                         String provider, String model,
                                         String unsupportedLanguageResponse) {
        public ClassificationResponse(
                String schemaVersion, UUID requestId, String correlationId,
                String intent, UUID selectedEntityId, String provider, String model) {
            this(schemaVersion, requestId, correlationId, intent, selectedEntityId,
                    provider, model, null);
        }
    }
}
