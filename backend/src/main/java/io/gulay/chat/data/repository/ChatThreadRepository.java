package io.gulay.chat.data.repository;

import io.gulay.chat.data.model.ChatThreadModel;
import jakarta.persistence.LockModeType;

import java.util.Optional;
import java.util.UUID;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;

public interface ChatThreadRepository extends JpaRepository<ChatThreadModel, UUID> {
    Page<ChatThreadModel> findByOwnerId(UUID ownerId, Pageable pageable);

    Optional<ChatThreadModel> findByIdAndOwnerId(UUID id, UUID ownerId);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    Optional<ChatThreadModel> findLockedByIdAndOwnerId(UUID id, UUID ownerId);
}
