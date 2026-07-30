CREATE TABLE execution_request (
    id UUID PRIMARY KEY,
    owner_user_id UUID NOT NULL REFERENCES app_user_reference(id),
    entity_id UUID NOT NULL REFERENCES business_entity(id),
    schema_version_id UUID NOT NULL REFERENCES entity_schema_version(id),
    execution_type VARCHAR(20) NOT NULL,
    status VARCHAR(40) NOT NULL,
    original_request TEXT NOT NULL,
    requested_language VARCHAR(12) NOT NULL,
    execution_order_version VARCHAR(20) NOT NULL,
    execution_order_json JSONB NOT NULL,
    authorization_snapshot JSONB NOT NULL,
    configuration_snapshot JSONB NOT NULL,
    idempotency_key VARCHAR(100) NOT NULL,
    request_fingerprint VARCHAR(64) NOT NULL,
    correlation_id VARCHAR(100) NOT NULL,
    requested_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT uk_execution_request_owner_idempotency UNIQUE(owner_user_id, idempotency_key),
    CONSTRAINT ck_execution_request_type CHECK (execution_type IN ('REPORT', 'ML')),
    CONSTRAINT ck_execution_request_status CHECK (status IN
        ('VALIDATED', 'QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')),
    CONSTRAINT ck_execution_request_original_length CHECK (char_length(original_request) <= 4000)
);

CREATE INDEX idx_execution_request_owner_requested
    ON execution_request(owner_user_id, requested_at DESC);

CREATE TABLE execution_status_history (
    id UUID PRIMARY KEY,
    event_id UUID NOT NULL UNIQUE,
    execution_id UUID NOT NULL REFERENCES execution_request(id),
    stage VARCHAR(40) NOT NULL,
    status VARCHAR(40) NOT NULL,
    progress INTEGER NOT NULL,
    message_code VARCHAR(120) NOT NULL,
    message_parameters JSONB NOT NULL,
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT ck_execution_history_progress CHECK (progress BETWEEN 0 AND 100)
);

CREATE INDEX idx_execution_status_history_execution_time
    ON execution_status_history(execution_id, occurred_at);

CREATE FUNCTION reject_execution_order_mutation() RETURNS trigger AS $$
BEGIN
    IF NEW.owner_user_id <> OLD.owner_user_id
       OR NEW.entity_id <> OLD.entity_id
       OR NEW.schema_version_id <> OLD.schema_version_id
       OR NEW.execution_type <> OLD.execution_type
       OR NEW.original_request <> OLD.original_request
       OR NEW.execution_order_version <> OLD.execution_order_version
       OR NEW.execution_order_json <> OLD.execution_order_json
       OR NEW.authorization_snapshot <> OLD.authorization_snapshot
       OR NEW.configuration_snapshot <> OLD.configuration_snapshot
       OR NEW.idempotency_key <> OLD.idempotency_key
       OR NEW.request_fingerprint <> OLD.request_fingerprint THEN
        RAISE EXCEPTION 'execution request planning snapshot is immutable';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_execution_request_immutable
BEFORE UPDATE ON execution_request
FOR EACH ROW EXECUTE FUNCTION reject_execution_order_mutation();
