package io.gulay.user.data.repository;

import io.gulay.user.data.model.AppUserReferenceModel;

import java.util.Optional;
import java.util.UUID;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AppUserReferenceRepository extends JpaRepository<AppUserReferenceModel, UUID> {

    Optional<AppUserReferenceModel> findByKeycloakUserId(String keycloakUserId);

    Page<AppUserReferenceModel> findByStatusNot(
            io.gulay.user.data.model.UserStatus status, Pageable pageable);
}
