CREATE TABLE execution_failure (
    id UUID PRIMARY KEY,
    execution_id UUID NOT NULL UNIQUE REFERENCES execution_request(id),
    schema_version VARCHAR(20) NOT NULL,
    failure_code VARCHAR(100) NOT NULL,
    failed_stage VARCHAR(100) NOT NULL,
    sanitized_technical_reason VARCHAR(1000) NOT NULL,
    user_explanation VARCHAR(2000) NOT NULL,
    explanation_status VARCHAR(20) NOT NULL
        CHECK (explanation_status IN ('COMPLETED', 'FAILED')),
    retryable BOOLEAN NOT NULL,
    language VARCHAR(2) NOT NULL CHECK (language IN ('tr', 'en')),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX idx_execution_failure_execution ON execution_failure(execution_id);
