package io.gulay.chat.data.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

import java.time.Instant;
import java.util.UUID;

import lombok.AccessLevel;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Entity
@Table(name = "chat_message")
@Getter
@Builder
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor(access = AccessLevel.PRIVATE)
public class ChatMessageModel {
    @Id
    private UUID id;
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "thread_id", nullable = false)
    private ChatThreadModel thread;
    @Column(name = "sequence_number", nullable = false)
    private long sequenceNumber;
    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private ChatRole role;
    @Column(nullable = false)
    private String content;
    private String provider;
    private String model;
    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private ChatMessageStatus status;
    @Column(name = "character_count", nullable = false)
    private int characterCount;
    @Column(name = "error_code")
    private String errorCode;
    @Column(name = "created_at", nullable = false)
    private Instant createdAt;
    @Column(name = "completed_at")
    private Instant completedAt;

    public void start(String providerName, String modelName) {
        status = ChatMessageStatus.STREAMING;
        provider = providerName;
        model = modelName;
    }

    public void complete(String finalContent, String providerName, String modelName, Instant now) {
        content = finalContent;
        characterCount = finalContent.length();
        provider = providerName;
        model = modelName;
        status = ChatMessageStatus.COMPLETED;
        completedAt = now;
        errorCode = null;
    }

    public void fail(String code, Instant now) {
        content = "";
        characterCount = 0;
        status = ChatMessageStatus.FAILED;
        completedAt = now;
        errorCode = code;
    }

}
