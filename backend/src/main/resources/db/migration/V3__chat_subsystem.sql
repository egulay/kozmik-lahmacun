CREATE TABLE chat_thread (
    id UUID PRIMARY KEY,
    owner_user_id UUID NOT NULL,
    title VARCHAR(200) NOT NULL,
    language VARCHAR(12) NOT NULL,
    status VARCHAR(32) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    deleted_at TIMESTAMP WITH TIME ZONE,
    retention_eligible_at TIMESTAMP WITH TIME ZONE,
    version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT fk_chat_thread_owner
        FOREIGN KEY (owner_user_id) REFERENCES app_user_reference (id),
    CONSTRAINT ck_chat_thread_status CHECK (status IN ('ACTIVE', 'ARCHIVED'))
);

CREATE TABLE chat_message (
    id UUID PRIMARY KEY,
    thread_id UUID NOT NULL,
    sequence_number BIGINT NOT NULL,
    role VARCHAR(32) NOT NULL,
    content TEXT NOT NULL,
    provider VARCHAR(80),
    model VARCHAR(160),
    status VARCHAR(32) NOT NULL,
    character_count INTEGER NOT NULL,
    error_code VARCHAR(120),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    completed_at TIMESTAMP WITH TIME ZONE,
    deleted_at TIMESTAMP WITH TIME ZONE,
    retention_eligible_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT uk_chat_message_sequence UNIQUE (thread_id, sequence_number),
    CONSTRAINT fk_chat_message_thread
        FOREIGN KEY (thread_id) REFERENCES chat_thread (id),
    CONSTRAINT ck_chat_message_role CHECK (role IN ('USER', 'ASSISTANT')),
    CONSTRAINT ck_chat_message_status
        CHECK (status IN ('COMPLETED', 'PENDING', 'STREAMING', 'FAILED')),
    CONSTRAINT ck_chat_message_size CHECK (character_count >= 0 AND character_count <= 20000)
);

CREATE INDEX idx_chat_thread_owner_updated
    ON chat_thread (owner_user_id, updated_at DESC)
    WHERE deleted_at IS NULL;
CREATE INDEX idx_chat_message_thread_sequence
    ON chat_message (thread_id, sequence_number)
    WHERE deleted_at IS NULL;
