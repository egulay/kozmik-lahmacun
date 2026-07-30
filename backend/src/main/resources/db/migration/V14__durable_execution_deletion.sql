CREATE TABLE execution_deletion_job (
    id UUID PRIMARY KEY,
    execution_id UUID NOT NULL UNIQUE,
    requested_by UUID NOT NULL REFERENCES app_user_reference(id),
    correlation_id VARCHAR(100) NOT NULL,
    actor_role VARCHAR(20) NOT NULL,
    status VARCHAR(30) NOT NULL
        CHECK (status IN ('PENDING', 'PROCESSING', 'RETRY_PENDING', 'COMPLETED')),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    requested_at TIMESTAMP WITH TIME ZONE NOT NULL,
    next_attempt_at TIMESTAMP WITH TIME ZONE NOT NULL,
    completed_at TIMESTAMP WITH TIME ZONE,
    last_error_code VARCHAR(120)
);

CREATE TABLE execution_deletion_artifact (
    id UUID PRIMARY KEY,
    deletion_job_id UUID NOT NULL REFERENCES execution_deletion_job(id) ON DELETE CASCADE,
    artifact_id UUID NOT NULL,
    bucket_name VARCHAR(120) NOT NULL,
    object_key VARCHAR(1000) NOT NULL,
    UNIQUE (deletion_job_id, artifact_id),
    UNIQUE (bucket_name, object_key)
);

CREATE INDEX idx_execution_deletion_retry
    ON execution_deletion_job(next_attempt_at)
    WHERE status IN ('PENDING', 'PROCESSING', 'RETRY_PENDING');
