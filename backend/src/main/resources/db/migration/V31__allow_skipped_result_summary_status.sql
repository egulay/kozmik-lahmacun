ALTER TABLE execution_result
    DROP CONSTRAINT ck_execution_result_summary_status;

ALTER TABLE execution_result
    ADD CONSTRAINT ck_execution_result_summary_status
        CHECK (summary_status IN ('COMPLETED', 'FAILED', 'SKIPPED'));
