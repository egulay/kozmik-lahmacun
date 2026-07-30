package io.gulay.user.data.repository;

import io.gulay.user.data.model.UserManagementOperationModel;
import io.gulay.user.data.model.UserOperationStatus;

import java.time.Instant;
import java.util.Collection;
import java.util.List;
import java.util.UUID;

import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface UserManagementOperationRepository
        extends JpaRepository<UserManagementOperationModel, UUID> {
    List<UserManagementOperationModel> findByStatusInAndNextAttemptAtLessThanEqualOrderByRequestedAt(
            Collection<UserOperationStatus> statuses, Instant now, Pageable pageable);
}
