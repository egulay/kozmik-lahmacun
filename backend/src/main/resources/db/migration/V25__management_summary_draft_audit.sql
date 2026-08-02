ALTER TABLE execution_result
    ADD COLUMN summary_evidence_schema_version VARCHAR(20),
    ADD COLUMN summary_draft_json JSONB,
    ADD COLUMN summary_blocking_issues_json JSONB,
    ADD COLUMN summary_advisory_issues_json JSONB,
    ADD COLUMN summary_repair_attempt_count INTEGER,
    ADD COLUMN summary_provider VARCHAR(100),
    ADD COLUMN summary_provider_model VARCHAR(200),
    ADD COLUMN summary_generated_at TIMESTAMP WITH TIME ZONE;

UPDATE execution_result
   SET summary_validation_status = 'LEGACY_UNVALIDATED',
       summary_validation_issues_json = '["LEGACY_SUMMARY_NOT_REVALIDATED"]'::jsonb
 WHERE summary_status = 'COMPLETED';

UPDATE execution_result
   SET summary_evidence_schema_version = COALESCE(
           summary_evidence_json ->> 'schemaVersion', '2.0'),
       summary_blocking_issues_json = CASE
           WHEN summary_validation_status IN ('REJECTED', 'PROVIDER_FAILED')
               THEN summary_validation_issues_json
           ELSE '[]'::jsonb
       END,
       summary_advisory_issues_json = CASE
           WHEN summary_validation_status IN (
               'ACCEPTED_WITH_ADVISORIES', 'LEGACY_UNVALIDATED')
               THEN summary_validation_issues_json
           ELSE '[]'::jsonb
       END,
       summary_repair_attempt_count = 0,
       summary_provider = 'legacy',
       summary_provider_model = 'legacy',
       summary_generated_at = created_at;

ALTER TABLE execution_result
    ALTER COLUMN summary_evidence_schema_version SET NOT NULL,
    ALTER COLUMN summary_blocking_issues_json SET NOT NULL,
    ALTER COLUMN summary_advisory_issues_json SET NOT NULL,
    ALTER COLUMN summary_repair_attempt_count SET NOT NULL,
    ALTER COLUMN summary_provider SET NOT NULL,
    ALTER COLUMN summary_provider_model SET NOT NULL,
    ALTER COLUMN summary_generated_at SET NOT NULL,
    ADD CONSTRAINT ck_execution_result_summary_repair_attempts
        CHECK (summary_repair_attempt_count BETWEEN 0 AND 2),
    ADD CONSTRAINT ck_execution_result_summary_issue_arrays
        CHECK (
            jsonb_typeof(summary_blocking_issues_json) = 'array'
            AND jsonb_typeof(summary_advisory_issues_json) = 'array'
        ),
    ADD CONSTRAINT ck_execution_result_summary_draft
        CHECK (
            summary_validation_status = 'LEGACY_UNVALIDATED'
            OR summary_status = 'FAILED'
            OR (
                summary_draft_json IS NOT NULL
                AND jsonb_typeof(summary_draft_json) = 'object'
                AND summary_draft_json ->> 'schemaVersion' = '1.0'
            )
        );
