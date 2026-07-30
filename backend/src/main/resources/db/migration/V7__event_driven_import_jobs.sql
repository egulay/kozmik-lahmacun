CREATE TABLE import_job (
    id UUID PRIMARY KEY,
    source_event_id UUID NOT NULL UNIQUE,
    entity_id UUID NOT NULL REFERENCES business_entity(id),
    schema_version_id UUID REFERENCES entity_schema_version(id),
    source_type VARCHAR(40) NOT NULL,
    source_reference VARCHAR(1200) NOT NULL,
    status VARCHAR(40) NOT NULL,
    refined_bucket VARCHAR(120),
    refined_object_key VARCHAR(1000),
    row_count BIGINT CHECK (row_count IS NULL OR row_count >= 0),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    error_code VARCHAR(120),
    error_message VARCHAR(1000)
);

CREATE TABLE import_status_history (
    id UUID PRIMARY KEY,
    event_id UUID NOT NULL UNIQUE,
    import_job_id UUID NOT NULL REFERENCES import_job(id),
    stage VARCHAR(40) NOT NULL,
    status VARCHAR(40) NOT NULL,
    message_code VARCHAR(120) NOT NULL,
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX idx_import_job_entity_created ON import_job(entity_id, created_at DESC);
CREATE INDEX idx_import_history_job_time ON import_status_history(import_job_id, occurred_at);
