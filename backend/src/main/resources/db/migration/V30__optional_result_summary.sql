ALTER TABLE execution_result
    DROP CONSTRAINT ck_execution_result_summary_contract;

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
            OR
            (summary_status = 'SKIPPED'
                AND result_summary IS NULL
                AND summary_error_code IS NULL
                AND summary_provider = 'NOT_REQUESTED'
                AND summary_provider_model = 'NOT_REQUESTED')
        );
