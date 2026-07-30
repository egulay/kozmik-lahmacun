CREATE TABLE app_user_reference (
    id UUID PRIMARY KEY,
    keycloak_user_id VARCHAR(255) NOT NULL,
    display_name VARCHAR(255),
    email VARCHAR(320),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT uk_app_user_reference_keycloak_user UNIQUE (keycloak_user_id)
);

CREATE TABLE platform_setting (
    id UUID PRIMARY KEY,
    setting_key VARCHAR(160) NOT NULL,
    setting_scope VARCHAR(80) NOT NULL,
    value_type VARCHAR(40) NOT NULL,
    string_value TEXT,
    integer_value BIGINT,
    boolean_value BOOLEAN,
    json_value JSONB,
    version BIGINT NOT NULL DEFAULT 0,
    updated_by UUID,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT uk_platform_setting_key_scope UNIQUE (setting_key, setting_scope),
    CONSTRAINT fk_platform_setting_updated_by
        FOREIGN KEY (updated_by) REFERENCES app_user_reference (id),
    CONSTRAINT ck_platform_setting_exactly_one_value CHECK (
        num_nonnulls(string_value, integer_value, boolean_value, json_value) = 1
    ),
    CONSTRAINT ck_platform_setting_value_type CHECK (
        (value_type = 'STRING' AND string_value IS NOT NULL)
        OR (value_type = 'INTEGER' AND integer_value IS NOT NULL)
        OR (value_type = 'BOOLEAN' AND boolean_value IS NOT NULL)
        OR (value_type = 'JSON' AND json_value IS NOT NULL)
    )
);

CREATE TABLE audit_event (
    id UUID PRIMARY KEY,
    event_type VARCHAR(120) NOT NULL,
    actor_user_id UUID,
    subject_type VARCHAR(100),
    subject_id VARCHAR(255),
    correlation_id VARCHAR(100) NOT NULL,
    outcome VARCHAR(40) NOT NULL,
    detail_code VARCHAR(160),
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT fk_audit_event_actor
        FOREIGN KEY (actor_user_id) REFERENCES app_user_reference (id)
);

CREATE INDEX idx_audit_event_occurred_at ON audit_event (occurred_at);
CREATE INDEX idx_audit_event_actor_occurred_at
    ON audit_event (actor_user_id, occurred_at);

