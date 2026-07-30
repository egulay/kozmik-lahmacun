ALTER TABLE execution_request
    ADD COLUMN started_at TIMESTAMP WITH TIME ZONE,
    ADD COLUMN completed_at TIMESTAMP WITH TIME ZONE;

CREATE TABLE execution_command_outbox (
    id UUID PRIMARY KEY,
    event_id UUID NOT NULL UNIQUE,
    execution_id UUID NOT NULL UNIQUE REFERENCES execution_request(id),
    payload_json JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    published_at TIMESTAMP WITH TIME ZONE,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error_code VARCHAR(120)
);

CREATE INDEX idx_execution_command_outbox_pending
    ON execution_command_outbox(created_at) WHERE published_at IS NULL;

CREATE TABLE processed_execution_event (
    event_id UUID PRIMARY KEY,
    event_type VARCHAR(40) NOT NULL,
    execution_id UUID NOT NULL REFERENCES execution_request(id),
    processed_at TIMESTAMP WITH TIME ZONE NOT NULL
);
