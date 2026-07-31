package io.gulay.chat.data.repository;

import io.gulay.chat.data.model.ChatMessageModel;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

public interface ChatMessageRepository extends JpaRepository<ChatMessageModel, UUID> {
    Page<ChatMessageModel> findByThreadId(UUID threadId, Pageable pageable);

    List<ChatMessageModel> findByThreadIdAndStatus(
            UUID threadId, io.gulay.chat.data.model.ChatMessageStatus status,
            Pageable pageable);

    @Query("select coalesce(max(m.sequenceNumber), 0) from ChatMessageModel m where m.thread.id = :threadId")
    long maximumSequence(UUID threadId);

    Optional<ChatMessageModel> findByIdAndThreadId(UUID id, UUID threadId);
}
