package io.gulay.entity.data.model;

import io.gulay.user.data.model.AppUserReferenceModel;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

import java.time.Instant;
import java.util.UUID;

import lombok.AccessLevel;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Entity
@Table(name = "business_entity")
@Getter
@Builder
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor(access = AccessLevel.PRIVATE)
public class BusinessEntityModel {
    @Id
    private UUID id;
    @Column(nullable = false, unique = true)
    private String name;
    private String description;
    @Column(name = "name_tr")
    private String nameTr;
    @Column(name = "description_tr")
    private String descriptionTr;
    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private EntityStatus status;
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "created_by", updatable = false)
    private AppUserReferenceModel createdBy;
    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;
    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;
    @Version
    private long version;

    public void update(String name, String description, EntityStatus status, Instant now) {
        this.name = name;
        this.description = description;
        this.status = status;
        this.updatedAt = now;
    }

    public void localize(String localizedName, String localizedDescription, Instant now) {
        this.nameTr = localizedName;
        this.descriptionTr = localizedDescription;
        this.updatedAt = now;
    }
}
