package io.gulay.entity.api;

import lombok.val;

import io.gulay.entity.data.model.ColumnDataType;
import io.gulay.entity.dto.EntityDtos;
import jakarta.validation.Validation;
import jakarta.validation.ConstraintViolation;
import java.util.UUID;
import java.util.Set;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class EntityContractsValidationTest {

    @Test
    void rejectsUnsafePhysicalColumnNames() {
        val column = new EntityDtos.ColumnDefinition(
                UUID.randomUUID(), "customer email", "Customer email", ColumnDataType.STRING,
                null, 1);

        assertThat(validate(column))
                .extracting(violation -> violation.getPropertyPath().toString())
                .contains("columnName");
    }

    @Test
    void acceptsStructuralMetadata() {
        val column = new EntityDtos.ColumnDefinition(
                null, "customer_id", "Customer ID", ColumnDataType.LONG,
                "Stable identifier", 1);

        assertThat(validate(column)).isEmpty();
    }

    private Set<ConstraintViolation<EntityDtos.ColumnDefinition>> validate(
            EntityDtos.ColumnDefinition column) {
        try (val factory = Validation.buildDefaultValidatorFactory()) {
            return factory.getValidator().validate(column);
        }
    }
}
