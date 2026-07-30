-- A chat message has no lifecycle independent of its owning thread.
-- Enforce aggregate cleanup in PostgreSQL rather than relying on application code.
ALTER TABLE chat_message
    DROP CONSTRAINT fk_chat_message_thread,
    ADD CONSTRAINT fk_chat_message_thread
        FOREIGN KEY (thread_id) REFERENCES chat_thread(id) ON DELETE CASCADE;

-- Purge rows hidden by the previous soft-delete implementation. Their messages
-- are removed by the database cascade above.
DELETE FROM chat_thread
WHERE deleted_at IS NOT NULL;

DROP INDEX idx_chat_message_thread_sequence;
DROP INDEX idx_chat_thread_owner_updated;

ALTER TABLE chat_message
    DROP COLUMN deleted_at,
    DROP COLUMN retention_eligible_at;

ALTER TABLE chat_thread
    DROP COLUMN deleted_at,
    DROP COLUMN retention_eligible_at;

CREATE INDEX idx_chat_thread_owner_updated
    ON chat_thread (owner_user_id, updated_at DESC);

CREATE INDEX idx_chat_message_thread_sequence
    ON chat_message (thread_id, sequence_number);
