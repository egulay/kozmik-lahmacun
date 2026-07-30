package io.gulay.user.data.service;

import lombok.val;

import io.gulay.user.data.model.AppUserReferenceModel;
import io.gulay.user.data.repository.AppUserReferenceRepository;

import java.time.Clock;
import java.time.Instant;
import java.util.UUID;
import java.util.Set;

import io.gulay.user.data.model.UserRole;
import io.gulay.user.data.model.UserStatus;
import lombok.RequiredArgsConstructor;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
public class AppUserReferenceService {

    private final AppUserReferenceRepository repository;
    private final Clock clock;

    @Transactional
    public void synchronize(
            String keycloakUserId, String displayName, String email) {
        val now = Instant.now(clock);
        repository.findByKeycloakUserId(keycloakUserId)
                .map(existing -> refresh(existing, displayName, email, now))
                .orElseGet(() -> create(keycloakUserId, displayName, email, now));
    }

    @Transactional
    public AppUserReferenceModel synchronizeIdentity(
            String keycloakUserId, String username, String displayName, String email,
            Set<UserRole> roles, boolean enabled) {
        val now = Instant.now(clock);
        val user = repository.findByKeycloakUserId(keycloakUserId).orElseGet(() ->
                AppUserReferenceModel.builder()
                        .id(UUID.randomUUID()).keycloakUserId(keycloakUserId)
                        .username(username).displayName(displayName).email(email)
                        .status(enabled ? UserStatus.ACTIVE : UserStatus.SUSPENDED)
                        .roles(new java.util.LinkedHashSet<>(roles))
                        .createdAt(now).updatedAt(now).build());
        user.synchronizeFromIdentity(username, displayName, email, roles, enabled, now);
        return repository.save(user);
    }

    private AppUserReferenceModel refresh(
            AppUserReferenceModel existing, String displayName, String email, Instant now) {
        existing.refreshPresentation(displayName, email, now);
        return repository.save(existing);
    }

    private AppUserReferenceModel create(
            String keycloakUserId, String displayName, String email, Instant now) {
        val user = AppUserReferenceModel.builder()
                .id(UUID.randomUUID())
                .keycloakUserId(keycloakUserId)
                .displayName(displayName)
                .email(email)
                .status(UserStatus.ACTIVE)
                .roles(Set.of(UserRole.REPORTER))
                .createdAt(now)
                .updatedAt(now)
                .build();
        try {
            return repository.saveAndFlush(user);
        } catch (DataIntegrityViolationException concurrentInsert) {
            return repository.findByKeycloakUserId(keycloakUserId)
                    .map(existing -> refresh(existing, displayName, email, now))
                    .orElseThrow(() -> concurrentInsert);
        }
    }
}
