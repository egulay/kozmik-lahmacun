ALTER TABLE execution_result
    DROP CONSTRAINT ck_execution_result_summary_validation_status,
    DROP CONSTRAINT ck_execution_result_summary_disposition,
    DROP CONSTRAINT ck_execution_result_summary_repair_attempts,
    DROP CONSTRAINT ck_execution_result_summary_issue_arrays,
    DROP CONSTRAINT ck_execution_result_summary_audit;

ALTER TABLE execution_result
    DROP COLUMN summary_evidence_json,
    DROP COLUMN summary_validation_status,
    DROP COLUMN summary_validation_issues_json,
    DROP COLUMN summary_evidence_schema_version,
    DROP COLUMN summary_audit_json,
    DROP COLUMN summary_blocking_issues_json,
    DROP COLUMN summary_advisory_issues_json,
    DROP COLUMN summary_repair_attempt_count,
    ADD COLUMN summary_error_code VARCHAR(100);

ALTER TABLE execution_result
    ADD CONSTRAINT ck_execution_result_summary_contract
        CHECK (
            (summary_status = 'COMPLETED'
                AND result_summary IS NOT NULL
                AND summary_error_code IS NULL)
            OR
            (summary_status = 'FAILED'
                AND result_summary IS NULL
                AND summary_error_code IS NOT NULL)
        );
