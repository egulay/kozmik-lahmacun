package io.gulay.entity.data.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

import java.util.UUID;

import lombok.AccessLevel;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Entity
@Table(name = "entity_column")
@Getter
@Builder
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@AllArgsConstructor(access = AccessLevel.PRIVATE)
public class EntityColumnModel {
    @Id
    private UUID id;
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "entity_id", nullable = false, updatable = false)
    private BusinessEntityModel entity;
    @Column(name = "column_name", nullable = false, updatable = false)
    private String columnName;
    @Column(name = "business_name", nullable = false, updatable = false)
    private String businessName;
    @Column(name = "business_name_tr")
    private String businessNameTr;
    @Enumerated(EnumType.STRING)
    @Column(name = "data_type", nullable = false, updatable = false)
    private ColumnDataType dataType;
    @Column(updatable = false)
    private String description;
    @Column(name = "description_tr")
    private String descriptionTr;
    @Column(name = "ordinal_position", nullable = false, updatable = false)
    private int ordinalPosition;

    public void localize(String localizedBusinessName, String localizedDescription) {
        this.businessNameTr = localizedBusinessName;
        this.descriptionTr = localizedDescription;
    }
}
