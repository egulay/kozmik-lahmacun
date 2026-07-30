CREATE TABLE business_entity (
    id UUID PRIMARY KEY,
    name VARCHAR(160) NOT NULL,
    description TEXT,
    status VARCHAR(32) NOT NULL,
    reporting_enabled BOOLEAN NOT NULL,
    ml_enabled BOOLEAN NOT NULL,
    classification VARCHAR(32) NOT NULL,
    created_by UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT uk_business_entity_name UNIQUE (name),
    CONSTRAINT fk_business_entity_created_by
        FOREIGN KEY (created_by) REFERENCES app_user_reference (id),
    CONSTRAINT ck_business_entity_status
        CHECK (status IN ('ACTIVE', 'INACTIVE')),
    CONSTRAINT ck_business_entity_classification
        CHECK (classification IN ('PUBLIC', 'INTERNAL', 'CONFIDENTIAL', 'RESTRICTED'))
);

CREATE TABLE business_entity_access (
    id UUID PRIMARY KEY,
    entity_id UUID NOT NULL,
    user_id UUID NOT NULL,
    granted_by UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT uk_business_entity_access UNIQUE (entity_id, user_id),
    CONSTRAINT fk_business_entity_access_entity
        FOREIGN KEY (entity_id) REFERENCES business_entity (id),
    CONSTRAINT fk_business_entity_access_user
        FOREIGN KEY (user_id) REFERENCES app_user_reference (id),
    CONSTRAINT fk_business_entity_access_granted_by
        FOREIGN KEY (granted_by) REFERENCES app_user_reference (id)
);

CREATE TABLE entity_schema_version (
    id UUID PRIMARY KEY,
    entity_id UUID NOT NULL,
    version_number INTEGER NOT NULL,
    status VARCHAR(32) NOT NULL,
    effective_from TIMESTAMP WITH TIME ZONE,
    created_by UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    schema_snapshot JSONB NOT NULL,
    CONSTRAINT uk_entity_schema_version UNIQUE (entity_id, version_number),
    CONSTRAINT fk_entity_schema_version_entity
        FOREIGN KEY (entity_id) REFERENCES business_entity (id),
    CONSTRAINT fk_entity_schema_version_created_by
        FOREIGN KEY (created_by) REFERENCES app_user_reference (id),
    CONSTRAINT ck_entity_schema_version_number CHECK (version_number > 0),
    CONSTRAINT ck_entity_schema_version_status
        CHECK (status = 'PUBLISHED')
);

CREATE TABLE entity_column (
    id UUID PRIMARY KEY,
    schema_version_id UUID NOT NULL,
    column_name VARCHAR(160) NOT NULL,
    business_name VARCHAR(200) NOT NULL,
    data_type VARCHAR(32) NOT NULL,
    nullable BOOLEAN NOT NULL,
    classification VARCHAR(32) NOT NULL,
    description TEXT,
    ordinal_position INTEGER NOT NULL,
    reporting_eligible BOOLEAN NOT NULL,
    ml_feature_eligible BOOLEAN NOT NULL,
    ml_target_eligible BOOLEAN NOT NULL,
    CONSTRAINT uk_entity_column_name UNIQUE (schema_version_id, column_name),
    CONSTRAINT uk_entity_column_ordinal UNIQUE (schema_version_id, ordinal_position),
    CONSTRAINT fk_entity_column_schema
        FOREIGN KEY (schema_version_id) REFERENCES entity_schema_version (id),
    CONSTRAINT ck_entity_column_ordinal CHECK (ordinal_position > 0),
    CONSTRAINT ck_entity_column_data_type CHECK (
        data_type IN ('STRING', 'INTEGER', 'LONG', 'DECIMAL', 'BOOLEAN', 'DATE', 'TIMESTAMP')
    ),
    CONSTRAINT ck_entity_column_classification CHECK (
        classification IN ('PUBLIC', 'INTERNAL', 'CONFIDENTIAL', 'RESTRICTED')
    )
);

CREATE INDEX idx_business_entity_access_user
    ON business_entity_access (user_id, entity_id);
CREATE INDEX idx_entity_schema_entity_version
    ON entity_schema_version (entity_id, version_number DESC);
CREATE INDEX idx_entity_column_schema_ordinal
    ON entity_column (schema_version_id, ordinal_position);

ALTER TABLE business_entity
    ADD COLUMN current_schema_version_id UUID,
    ADD CONSTRAINT fk_business_entity_current_schema
        FOREIGN KEY (current_schema_version_id) REFERENCES entity_schema_version (id);

CREATE OR REPLACE FUNCTION reject_schema_history_mutation()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'historical schema versions and columns are immutable';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_schema_version_immutable
    BEFORE UPDATE OR DELETE ON entity_schema_version
    FOR EACH ROW EXECUTE FUNCTION reject_schema_history_mutation();

CREATE TRIGGER trg_entity_column_immutable
    BEFORE UPDATE OR DELETE ON entity_column
    FOR EACH ROW EXECUTE FUNCTION reject_schema_history_mutation();
