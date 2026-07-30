-- Deleted user tombstones may be physically removed without deleting governed
-- entity metadata. Creator provenance remains available through audit events.
ALTER TABLE business_entity
    ALTER COLUMN created_by DROP NOT NULL;

CREATE INDEX IF NOT EXISTS idx_execution_request_deleted_at
    ON execution_request(deleted_at)
    WHERE deleted_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_execution_artifact_deleted_at
    ON execution_artifact(deleted_at)
    WHERE deleted_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_app_user_reference_deleted_at
    ON app_user_reference(deleted_at)
    WHERE deleted_at IS NOT NULL;
