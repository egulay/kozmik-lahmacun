ALTER TABLE app_user_reference
    ADD COLUMN username VARCHAR(255),
    ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    ADD COLUMN deleted_at TIMESTAMP WITH TIME ZONE,
    ADD COLUMN version BIGINT NOT NULL DEFAULT 0,
    ADD CONSTRAINT ck_app_user_status CHECK (status IN ('ACTIVE', 'SUSPENDED', 'DELETED'));

CREATE TABLE app_user_role (
    user_id UUID NOT NULL REFERENCES app_user_reference(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL CHECK (role IN ('REPORTER', 'SCIENTIST', 'ADMIN')),
    PRIMARY KEY (user_id, role)
);

CREATE TABLE user_management_operation (
    id UUID PRIMARY KEY,
    target_user_id UUID NOT NULL REFERENCES app_user_reference(id),
    actor_user_id UUID NOT NULL REFERENCES app_user_reference(id),
    operation_type VARCHAR(20) NOT NULL
        CHECK (operation_type IN ('UPDATE', 'SUSPEND', 'RESUME', 'DELETE')),
    desired_display_name VARCHAR(255),
    desired_email VARCHAR(320),
    desired_roles VARCHAR(255),
    status VARCHAR(30) NOT NULL
        CHECK (status IN ('PENDING', 'PROCESSING', 'RETRY_PENDING', 'COMPLETED')),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMP WITH TIME ZONE NOT NULL,
    correlation_id VARCHAR(100) NOT NULL UNIQUE,
    last_error_code VARCHAR(120),
    requested_at TIMESTAMP WITH TIME ZONE NOT NULL,
    completed_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_user_management_operation_retry
    ON user_management_operation(status, next_attempt_at);
