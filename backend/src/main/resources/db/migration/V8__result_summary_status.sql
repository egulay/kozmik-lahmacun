ALTER TABLE execution_result
    ADD COLUMN summary_status VARCHAR(40) NOT NULL DEFAULT 'FAILED',
    ADD CONSTRAINT ck_execution_result_summary_status
        CHECK (summary_status IN ('COMPLETED', 'FAILED'));

ALTER TABLE execution_result ALTER COLUMN summary_status DROP DEFAULT;
