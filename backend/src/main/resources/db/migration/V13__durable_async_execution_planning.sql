ALTER TABLE execution_request
    DROP CONSTRAINT ck_execution_request_status;

ALTER TABLE execution_request
    ADD CONSTRAINT ck_execution_request_status CHECK (status IN
        ('PLANNING', 'VALIDATED', 'QUEUED', 'RUNNING',
         'SUCCEEDED', 'FAILED', 'CANCELLED', 'TIMED_OUT'));

CREATE OR REPLACE FUNCTION reject_execution_order_mutation() RETURNS trigger AS $$
BEGIN
    IF NEW.owner_user_id <> OLD.owner_user_id
       OR NEW.entity_id <> OLD.entity_id
       OR NEW.schema_version_id <> OLD.schema_version_id
       OR NEW.execution_type <> OLD.execution_type
       OR NEW.original_request <> OLD.original_request
       OR NEW.authorization_snapshot <> OLD.authorization_snapshot
       OR NEW.configuration_snapshot <> OLD.configuration_snapshot
       OR NEW.idempotency_key <> OLD.idempotency_key
       OR NEW.request_fingerprint <> OLD.request_fingerprint THEN
        RAISE EXCEPTION 'execution request identity and authorization snapshot are immutable';
    END IF;

    IF OLD.status = 'PLANNING'
       AND OLD.execution_order_version = 'PENDING'
       AND OLD.execution_order_json = '{}'::jsonb
       AND NEW.status = 'VALIDATED' THEN
        IF NEW.execution_order_version = 'PENDING'
           OR NEW.execution_order_json = '{}'::jsonb THEN
            RAISE EXCEPTION 'validated execution requires a completed order snapshot';
        END IF;
        RETURN NEW;
    END IF;

    IF NEW.execution_order_version <> OLD.execution_order_version
       OR NEW.execution_order_json <> OLD.execution_order_json THEN
        RAISE EXCEPTION 'execution request planning snapshot is immutable';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
