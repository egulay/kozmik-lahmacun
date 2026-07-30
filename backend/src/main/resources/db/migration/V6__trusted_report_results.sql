CREATE TABLE execution_result (
    id UUID PRIMARY KEY,
    execution_id UUID NOT NULL UNIQUE REFERENCES execution_request(id),
    schema_version VARCHAR(20) NOT NULL,
    row_count BIGINT NOT NULL CHECK (row_count >= 0),
    preview_json JSONB NOT NULL,
    kpis_json JSONB NOT NULL,
    charts_json JSONB NOT NULL,
    warnings_json JSONB NOT NULL,
    management_summary VARCHAR(4000),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE execution_artifact (
    id UUID PRIMARY KEY,
    execution_result_id UUID NOT NULL REFERENCES execution_result(id),
    format VARCHAR(40) NOT NULL,
    bucket_name VARCHAR(120) NOT NULL,
    object_key VARCHAR(1000) NOT NULL,
    size_bytes BIGINT CHECK (size_bytes IS NULL OR size_bytes >= 0),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    UNIQUE (bucket_name, object_key)
);

CREATE INDEX idx_execution_artifact_result ON execution_artifact(execution_result_id);
