package io.gulay.user.data.repository;

import io.gulay.user.data.model.AppUserReferenceModel;

import java.util.Optional;
import java.util.Set;
import java.util.UUID;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

public interface AppUserReferenceRepository extends JpaRepository<AppUserReferenceModel, UUID> {

    Optional<AppUserReferenceModel> findByKeycloakUserId(String keycloakUserId);

    @Query("""
            select distinct u from AppUserReferenceModel u
            left join u.roles role
            where u.status in :statuses
              and (
                :search = ''
                or lower(coalesce(u.displayName, '')) like lower(concat('%', :search, '%'))
                or lower(coalesce(u.email, '')) like lower(concat('%', :search, '%'))
                or lower(coalesce(u.username, '')) like lower(concat('%', :search, '%'))
                or lower(cast(u.id as string)) like lower(concat('%', :search, '%'))
                or lower(cast(u.status as string)) like lower(concat('%', :search, '%'))
                or lower(cast(role as string)) like lower(concat('%', :search, '%'))
              )
            """)
    Page<AppUserReferenceModel> findFilteredPage(
            Set<io.gulay.user.data.model.UserStatus> statuses,
            String search, Pageable pageable);
}
