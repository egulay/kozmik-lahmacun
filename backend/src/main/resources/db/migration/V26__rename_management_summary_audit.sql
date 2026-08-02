ALTER TABLE execution_result
    RENAME COLUMN summary_draft_json TO summary_audit_json;

ALTER TABLE execution_result
    RENAME CONSTRAINT ck_execution_result_summary_draft
    TO ck_execution_result_summary_audit;
