ALTER TABLE business_entity DROP CONSTRAINT ck_business_entity_status;
ALTER TABLE business_entity ADD CONSTRAINT ck_business_entity_status
    CHECK (status IN ('ACTIVE', 'INACTIVE', 'DELETION_PENDING'));

CREATE TABLE deleted_entity_tombstone (
    entity_id UUID PRIMARY KEY,
    entity_name VARCHAR(160) NOT NULL,
    schema_snapshot JSONB NOT NULL,
    deleted_by UUID NOT NULL REFERENCES app_user_reference(id),
    requested_at TIMESTAMP WITH TIME ZONE NOT NULL,
    deleted_at TIMESTAMP WITH TIME ZONE,
    correlation_id VARCHAR(100) NOT NULL
);

CREATE TABLE entity_deletion_job (
    id UUID PRIMARY KEY,
    entity_id UUID NOT NULL UNIQUE REFERENCES business_entity(id),
    requested_by UUID NOT NULL REFERENCES app_user_reference(id),
    correlation_id VARCHAR(100) NOT NULL,
    status VARCHAR(30) NOT NULL CHECK (status IN
        ('WAITING_FOR_IDLE', 'DELETING', 'RETRY_PENDING', 'COMPLETED')),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    requested_at TIMESTAMP WITH TIME ZONE NOT NULL,
    next_attempt_at TIMESTAMP WITH TIME ZONE NOT NULL,
    completed_at TIMESTAMP WITH TIME ZONE,
    last_error_code VARCHAR(120)
);
CREATE INDEX idx_entity_deletion_ready ON entity_deletion_job(status, next_attempt_at);

CREATE OR REPLACE FUNCTION reject_entity_structure_mutation() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' AND EXISTS (
        SELECT 1 FROM deleted_entity_tombstone WHERE entity_id = OLD.entity_id
    ) THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'an entity structure is immutable; register a new entity UUID';
END;
$$ LANGUAGE plpgsql;
