package io.gulay.user.data.model;

import jakarta.persistence.Column;
import jakarta.persistence.CollectionTable;
import jakarta.persistence.ElementCollection;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

import java.time.Instant;
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.UUID;

import lombok.AccessLevel;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Entity
@Table(name = "app_user_reference")
@Getter
@Builder(toBuilder = true)
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor(access = AccessLevel.PRIVATE)
public class AppUserReferenceModel {

    @Id
    private UUID id;

    @Column(name = "keycloak_user_id", nullable = false, unique = true, updatable = false)
    private String keycloakUserId;

    @Column(name = "username")
    private String username;

    @Column(name = "display_name")
    private String displayName;

    @Column(name = "email")
    private String email;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    @Builder.Default
    private UserStatus status = UserStatus.ACTIVE;

    @ElementCollection(fetch = FetchType.EAGER)
    @CollectionTable(name = "app_user_role", joinColumns = @JoinColumn(name = "user_id"))
    @Column(name = "role")
    @Enumerated(EnumType.STRING)
    @Builder.Default
    private Set<UserRole> roles = new LinkedHashSet<>();

    @Column(name = "deleted_at")
    private Instant deletedAt;

    @Version
    private long version;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    public void refreshPresentation(String newDisplayName, String newEmail, Instant now) {
        if (status == UserStatus.DELETED) {
            return;
        }
        displayName = newDisplayName;
        email = newEmail;
        updatedAt = now;
    }

    public void synchronizeFromIdentity(
            String newUsername, String newDisplayName, String newEmail,
            Set<UserRole> newRoles, boolean enabled, Instant now) {
        if (status == UserStatus.DELETED) return;
        username = newUsername;
        displayName = newDisplayName;
        email = newEmail;
        roles.clear();
        roles.addAll(newRoles);
        status = enabled ? UserStatus.ACTIVE : UserStatus.SUSPENDED;
        updatedAt = now;
    }

    public void applyManagementState(
            String newUsername, String newDisplayName, String newEmail, Set<UserRole> newRoles,
            UserStatus newStatus, Instant now) {
        username = newUsername;
        displayName = newDisplayName;
        email = newEmail;
        roles.clear();
        roles.addAll(newRoles);
        status = newStatus;
        if (newStatus == UserStatus.DELETED) {
            username = "deleted-" + id;
            displayName = "Deleted user";
            email = null;
            deletedAt = now;
        }
        updatedAt = now;
    }
}
