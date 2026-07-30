package io.gulay.chat.data.service;

import lombok.val;

import io.gulay.api.ConflictException;
import io.gulay.api.ResourceNotFoundException;
import io.gulay.chat.client.PythonChatContracts;
import io.gulay.chat.data.model.ChatMessageModel;
import io.gulay.chat.data.model.ChatMessageStatus;
import io.gulay.chat.data.model.ChatRole;
import io.gulay.chat.data.model.ChatThreadModel;
import io.gulay.chat.data.model.ChatThreadStatus;
import io.gulay.chat.data.repository.ChatMessageRepository;
import io.gulay.chat.data.repository.ChatThreadRepository;
import io.gulay.chat.dto.ChatDtos;
import io.gulay.user.data.model.AppUserReferenceModel;
import io.gulay.user.data.repository.AppUserReferenceRepository;

import java.time.Clock;
import java.time.Instant;
import java.util.ArrayDeque;
import java.util.List;
import java.util.UUID;

import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
public class ChatService {
    private static final int MAX_HISTORY_MESSAGES = 20;
    private static final int MAX_HISTORY_CHARACTERS = 12_000;
    private final ChatThreadRepository threadRepository;
    private final ChatMessageRepository messageRepository;
    private final AppUserReferenceRepository userRepository;
    private final Clock clock;

    @Transactional
    public ChatDtos.ThreadResponse createThread(
            String keycloakUserId, ChatDtos.CreateThreadRequest request) {
        val now = Instant.now(clock);
        val thread = threadRepository.save(ChatThreadModel.builder()
                .id(UUID.randomUUID())
                .owner(user(keycloakUserId))
                .title(request.title().trim())
                .language(request.language())
                .status(ChatThreadStatus.ACTIVE)
                .createdAt(now)
                .updatedAt(now)
                .build());
        return response(thread);
    }

    @Transactional(readOnly = true)
    public ChatDtos.ThreadListResponse listThreads(
            String keycloakUserId, int page, int size) {
        val pageable = PageRequest.of(page, size, Sort.by(
                Sort.Order.desc("updatedAt"), Sort.Order.desc("id")));
        val threads = threadRepository.findByOwnerId(
                user(keycloakUserId).getId(), pageable);
        return new ChatDtos.ThreadListResponse(
                ChatDtos.VERSION,
                threads.getContent().stream().map(this::response).toList(),
                threads.getNumber(),
                threads.getSize(),
                threads.getTotalElements(),
                threads.getTotalPages(),
                threads.isFirst(),
                threads.isLast());
    }

    @Transactional(readOnly = true)
    public ChatDtos.MessageListResponse messages(UUID threadId, String keycloakUserId) {
        owned(threadId, keycloakUserId);
        return new ChatDtos.MessageListResponse(ChatDtos.VERSION,
                messageRepository.findByThreadIdOrderBySequenceNumber(threadId)
                        .stream().map(this::response).toList());
    }

    @Transactional
    public void deleteThread(UUID threadId, String keycloakUserId) {
        val owner = user(keycloakUserId);
        val thread = threadRepository
                .findLockedByIdAndOwnerId(threadId, owner.getId())
                .orElseThrow(() -> new ResourceNotFoundException("Chat thread not found"));
        threadRepository.delete(thread);
    }

    @Transactional
    public PostedMessages post(
            UUID threadId, String keycloakUserId, ChatDtos.PostMessageRequest request) {
        val owner = user(keycloakUserId);
        val thread = threadRepository
                .findLockedByIdAndOwnerId(threadId, owner.getId())
                .orElseThrow(() -> new ResourceNotFoundException("Chat thread not found"));
        if (thread.getStatus() != ChatThreadStatus.ACTIVE) {
            throw new ConflictException("Chat thread is not active");
        }
        val now = Instant.now(clock);
        val next = messageRepository.maximumSequence(threadId) + 1;
        val userMessage = messageRepository.save(ChatMessageModel.builder()
                .id(UUID.randomUUID()).thread(thread).sequenceNumber(next).role(ChatRole.USER)
                .content(request.content()).status(ChatMessageStatus.COMPLETED)
                .characterCount(request.content().length()).createdAt(now).completedAt(now).build());
        val assistant = messageRepository.save(ChatMessageModel.builder()
                .id(UUID.randomUUID()).thread(thread).sequenceNumber(next + 1)
                .role(ChatRole.ASSISTANT).content("").status(ChatMessageStatus.PENDING)
                .characterCount(0).createdAt(now).build());
        thread.touch(now);
        return new PostedMessages(
                new ChatDtos.PostedMessageResponse(
                        ChatDtos.VERSION, response(userMessage), response(assistant)),
                buildRequest(thread, assistant, request.language()));
    }

    @Transactional
    public void markStreaming(UUID messageId, String provider, String model) {
        val message = requiredMessage(messageId);
        if (message.getStatus() == ChatMessageStatus.PENDING) {
            message.start(provider, model);
        }
    }

    @Transactional
    public void complete(UUID messageId, String content, String provider, String model) {
        if (content.length() > 20_000) {
            throw new IllegalArgumentException("Assistant response exceeds durable message bound");
        }
        requiredMessage(messageId).complete(content, provider, model, Instant.now(clock));
    }

    @Transactional
    public void fail(UUID messageId, String errorCode) {
        val message = requiredMessage(messageId);
        if (message.getStatus() != ChatMessageStatus.COMPLETED) {
            message.fail(errorCode, Instant.now(clock));
        }
    }

    @Transactional(readOnly = true)
    public ChatMessageModel terminalOrCurrent(UUID threadId, UUID messageId, String keycloakUserId) {
        owned(threadId, keycloakUserId);
        return messageRepository.findByIdAndThreadId(messageId, threadId)
                .filter(message -> message.getRole() == ChatRole.ASSISTANT)
                .orElseThrow(() -> new ResourceNotFoundException("Assistant message not found"));
    }

    private PythonChatContracts.StreamRequest buildRequest(
            ChatThreadModel thread, ChatMessageModel assistant, String requestedLanguage) {
        val all = messageRepository.findByThreadIdOrderBySequenceNumber(
                thread.getId());
        val selected = new ArrayDeque<PythonChatContracts.HistoryMessage>();
        var characters = 0;
        for (var index = all.size() - 1; index >= 0 && selected.size() < MAX_HISTORY_MESSAGES; index--) {
            val message = all.get(index);
            if (message.getStatus() != ChatMessageStatus.COMPLETED) {
                continue;
            }
            if (characters + message.getCharacterCount() > MAX_HISTORY_CHARACTERS) {
                break;
            }
            selected.addFirst(new PythonChatContracts.HistoryMessage(
                    message.getRole().name().toLowerCase(), message.getContent()));
            characters += message.getCharacterCount();
        }
        return new PythonChatContracts.StreamRequest(
                "1.0", UUID.randomUUID(), thread.getId(), assistant.getId(),
                thread.getOwner().getId(), null,
                requestedLanguage, List.of(), List.copyOf(selected));
    }

    private void owned(UUID id, String keycloakUserId) {
        threadRepository.findByIdAndOwnerId(id, user(keycloakUserId).getId())
                .orElseThrow(() -> new ResourceNotFoundException("Chat thread not found"));
    }

    private AppUserReferenceModel user(String keycloakId) {
        return userRepository.findByKeycloakUserId(keycloakId)
                .orElseThrow(() -> new ResourceNotFoundException("User reference not found"));
    }

    private ChatMessageModel requiredMessage(UUID id) {
        return messageRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Chat message not found"));
    }

    ChatDtos.ThreadResponse response(ChatThreadModel thread) {
        return new ChatDtos.ThreadResponse(ChatDtos.VERSION, thread.getId(),
                thread.getTitle(), thread.getLanguage(), thread.getStatus(),
                thread.getCreatedAt(), thread.getUpdatedAt());
    }

    public ChatDtos.MessageResponse response(ChatMessageModel message) {
        return new ChatDtos.MessageResponse(ChatDtos.VERSION, message.getId(),
                message.getThread().getId(), message.getSequenceNumber(), message.getRole(),
                message.getContent(), message.getProvider(), message.getModel(),
                message.getStatus(), message.getErrorCode(), message.getCreatedAt(),
                message.getCompletedAt());
    }

    public record PostedMessages(
            ChatDtos.PostedMessageResponse response,
            PythonChatContracts.StreamRequest streamRequest) {
    }
}
