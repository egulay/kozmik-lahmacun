-- An entity UUID is the immutable data-structure identity. A changed structure
-- is registered as a new entity UUID; there are no entity schema versions.

DROP TRIGGER IF EXISTS trg_entity_column_immutable ON entity_column;
DROP TRIGGER IF EXISTS trg_schema_version_immutable ON entity_schema_version;
DROP FUNCTION IF EXISTS reject_schema_history_mutation();

-- Retain only the currently published definition when upgrading an older
-- database, then attach columns directly to their entity.
DELETE FROM entity_column c
WHERE NOT EXISTS (
    SELECT 1
    FROM business_entity e
    WHERE e.current_schema_version_id = c.schema_version_id
);

ALTER TABLE entity_column ADD COLUMN entity_id UUID;
UPDATE entity_column c
SET entity_id = s.entity_id
FROM entity_schema_version s
WHERE s.id = c.schema_version_id;
ALTER TABLE entity_column ALTER COLUMN entity_id SET NOT NULL;
ALTER TABLE entity_column
    ADD CONSTRAINT fk_entity_column_entity
        FOREIGN KEY (entity_id) REFERENCES business_entity(id);

ALTER TABLE entity_column DROP CONSTRAINT uk_entity_column_name;
ALTER TABLE entity_column DROP CONSTRAINT uk_entity_column_ordinal;
ALTER TABLE entity_column DROP CONSTRAINT fk_entity_column_schema;
DROP INDEX IF EXISTS idx_entity_column_schema_ordinal;
ALTER TABLE entity_column
    DROP COLUMN schema_version_id,
    DROP COLUMN nullable,
    DROP COLUMN classification,
    DROP COLUMN reporting_eligible,
    DROP COLUMN ml_feature_eligible,
    DROP COLUMN ml_target_eligible;
ALTER TABLE entity_column
    ADD CONSTRAINT uk_entity_column_name UNIQUE (entity_id, column_name),
    ADD CONSTRAINT uk_entity_column_ordinal UNIQUE (entity_id, ordinal_position);
CREATE INDEX idx_entity_column_entity_ordinal
    ON entity_column(entity_id, ordinal_position);

CREATE FUNCTION reject_entity_structure_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'an entity structure is immutable; register a new entity UUID';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_entity_column_immutable
    BEFORE UPDATE OR DELETE ON entity_column
    FOR EACH ROW EXECUTE FUNCTION reject_entity_structure_mutation();

DROP TRIGGER IF EXISTS trg_execution_request_immutable ON execution_request;
ALTER TABLE execution_request
    DROP CONSTRAINT IF EXISTS execution_request_schema_version_id_fkey,
    DROP COLUMN schema_version_id;

CREATE OR REPLACE FUNCTION reject_execution_order_mutation() RETURNS trigger AS $$
BEGIN
    IF NEW.owner_user_id <> OLD.owner_user_id
       OR NEW.entity_id <> OLD.entity_id
       OR NEW.execution_type <> OLD.execution_type
       OR NEW.original_request <> OLD.original_request
       OR NEW.authorization_snapshot <> OLD.authorization_snapshot
       OR NEW.configuration_snapshot <> OLD.configuration_snapshot
       OR NEW.idempotency_key <> OLD.idempotency_key
       OR NEW.request_fingerprint <> OLD.request_fingerprint THEN
        RAISE EXCEPTION 'execution request identity and authorization snapshot are immutable';
    END IF;

    IF OLD.status = 'PLANNING'
       AND OLD.execution_order_version = 'PENDING'
       AND OLD.execution_order_json = '{}'::jsonb
       AND NEW.status = 'VALIDATED' THEN
        IF NEW.execution_order_version = 'PENDING'
           OR NEW.execution_order_json = '{}'::jsonb THEN
            RAISE EXCEPTION 'validated execution requires a completed order snapshot';
        END IF;
        RETURN NEW;
    END IF;

    IF NEW.execution_order_version <> OLD.execution_order_version
       OR NEW.execution_order_json <> OLD.execution_order_json THEN
        RAISE EXCEPTION 'execution request planning snapshot is immutable';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_execution_request_immutable
BEFORE UPDATE ON execution_request
FOR EACH ROW EXECUTE FUNCTION reject_execution_order_mutation();

ALTER TABLE import_job
    DROP CONSTRAINT IF EXISTS import_job_schema_version_id_fkey,
    DROP COLUMN schema_version_id;
ALTER TABLE ingestion_stream
    DROP CONSTRAINT IF EXISTS ingestion_stream_schema_version_id_fkey,
    DROP COLUMN schema_version_id,
    DROP COLUMN last_chunk_id,
    DROP COLUMN last_watermark,
    DROP COLUMN stopped_at;

ALTER TABLE business_entity
    DROP CONSTRAINT fk_business_entity_current_schema,
    DROP COLUMN current_schema_version_id,
    DROP COLUMN reporting_enabled,
    DROP COLUMN ml_enabled,
    DROP COLUMN classification;

DROP TABLE business_entity_access;
DROP TABLE entity_schema_version;
