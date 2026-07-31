CREATE TABLE entity_column_category_value (
    id UUID PRIMARY KEY,
    entity_column_id UUID NOT NULL,
    category_value VARCHAR(500) NOT NULL,
    CONSTRAINT fk_entity_column_category_value_column
        FOREIGN KEY (entity_column_id) REFERENCES entity_column(id) ON DELETE CASCADE,
    CONSTRAINT uk_entity_column_category_value
        UNIQUE (entity_column_id, category_value)
);

CREATE INDEX idx_entity_column_category_value_column
    ON entity_column_category_value(entity_column_id);
