ALTER TABLE execution_result
    ADD COLUMN summary_evidence_json JSONB,
    ADD COLUMN summary_validation_status VARCHAR(40),
    ADD COLUMN summary_validation_issues_json JSONB;

UPDATE execution_result
   SET summary_evidence_json = '{"schemaVersion":"2.0","legacy":true}'::jsonb,
       summary_validation_status = CASE
           WHEN summary_status = 'COMPLETED' THEN 'LEGACY_UNVALIDATED'
           ELSE 'PROVIDER_FAILED'
       END,
       summary_validation_issues_json = CASE
           WHEN summary_status = 'COMPLETED'
               THEN '["LEGACY_SUMMARY_NOT_REVALIDATED"]'::jsonb
           ELSE '["SUMMARY_PROVIDER_FAILED"]'::jsonb
       END;

ALTER TABLE execution_result
    ALTER COLUMN summary_evidence_json SET NOT NULL,
    ALTER COLUMN summary_validation_status SET NOT NULL,
    ALTER COLUMN summary_validation_issues_json SET NOT NULL,
    ADD CONSTRAINT ck_execution_result_summary_validation_status
        CHECK (summary_validation_status IN (
            'ACCEPTED', 'ACCEPTED_WITH_ADVISORIES', 'REJECTED', 'PROVIDER_FAILED',
            'LEGACY_UNVALIDATED'
        )),
    ADD CONSTRAINT ck_execution_result_summary_disposition
        CHECK (
            (summary_status = 'COMPLETED'
                AND summary_validation_status IN (
                    'ACCEPTED', 'ACCEPTED_WITH_ADVISORIES', 'LEGACY_UNVALIDATED'
                ))
            OR
            (summary_status = 'FAILED'
                AND summary_validation_status IN ('REJECTED', 'PROVIDER_FAILED'))
        );
