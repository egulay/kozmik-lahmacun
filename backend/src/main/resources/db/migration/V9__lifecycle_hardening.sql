ALTER TABLE execution_request
    ADD COLUMN cancel_requested_at TIMESTAMP WITH TIME ZONE,
    ADD COLUMN timeout_at TIMESTAMP WITH TIME ZONE,
    ADD COLUMN retention_eligible_at TIMESTAMP WITH TIME ZONE,
    ADD COLUMN deleted_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE execution_request DROP CONSTRAINT ck_execution_request_status;
ALTER TABLE execution_request ADD CONSTRAINT ck_execution_request_status CHECK (status IN
    ('VALIDATED', 'QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED', 'TIMED_OUT'));
CREATE INDEX idx_execution_request_timeout ON execution_request(timeout_at)
    WHERE completed_at IS NULL;
CREATE INDEX idx_execution_request_retention ON execution_request(retention_eligible_at)
    WHERE deleted_at IS NULL;

ALTER TABLE execution_result
    ADD COLUMN preview_deleted_at TIMESTAMP WITH TIME ZONE,
    ADD COLUMN retention_eligible_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE execution_artifact
    ADD COLUMN retention_eligible_at TIMESTAMP WITH TIME ZONE,
    ADD COLUMN deleted_at TIMESTAMP WITH TIME ZONE,
    ADD COLUMN deletion_error_code VARCHAR(120);

CREATE TABLE executor_restart_command (
    id UUID PRIMARY KEY,
    nonce VARCHAR(120) NOT NULL UNIQUE,
    requested_by UUID NOT NULL REFERENCES app_user_reference(id),
    correlation_id VARCHAR(100) NOT NULL,
    status VARCHAR(40) NOT NULL,
    issued_at TIMESTAMP WITH TIME ZONE NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    completed_at TIMESTAMP WITH TIME ZONE,
    detail_code VARCHAR(120),
    CONSTRAINT ck_executor_restart_status CHECK
        (status IN ('REQUESTED', 'ACCEPTED', 'FAILED'))
);

INSERT INTO platform_setting
    (id, setting_key, setting_scope, value_type, integer_value, version, updated_at)
VALUES
    ('13000000-0000-4000-8000-000000000001', 'retention.chat_days', 'GLOBAL',
     'INTEGER', 30, 0, CURRENT_TIMESTAMP),
    ('13000000-0000-4000-8000-000000000002', 'retention.execution_days', 'GLOBAL',
     'INTEGER', 90, 0, CURRENT_TIMESTAMP),
    ('13000000-0000-4000-8000-000000000003', 'retention.preview_days', 'GLOBAL',
     'INTEGER', 30, 0, CURRENT_TIMESTAMP),
    ('13000000-0000-4000-8000-000000000004', 'retention.artifact_days', 'GLOBAL',
     'INTEGER', 90, 0, CURRENT_TIMESTAMP)
ON CONFLICT (setting_key, setting_scope) DO NOTHING;
