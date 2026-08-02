ALTER TABLE execution_result
    DROP CONSTRAINT ck_execution_result_summary_audit;

UPDATE execution_result
   SET summary_audit_json = jsonb_build_object(
           'schemaVersion', '2.0',
           'language', summary_audit_json -> 'language',
           'prose', COALESCE(
               summary_audit_json #> '{claims,0,prose}',
               to_jsonb(management_summary)
           ),
           'evidenceIds', COALESCE(
               summary_audit_json #> '{claims,0,evidenceIds}',
               '[]'::jsonb
           ),
           'scope', COALESCE(
               summary_audit_json #> '{claims,0,scope}',
               '{}'::jsonb
           )
       )
 WHERE summary_audit_json IS NOT NULL
   AND summary_audit_json ->> 'schemaVersion' = '1.0';

ALTER TABLE execution_result
    ADD CONSTRAINT ck_execution_result_summary_audit
        CHECK (
            summary_validation_status = 'LEGACY_UNVALIDATED'
            OR summary_status = 'FAILED'
            OR (
                summary_audit_json IS NOT NULL
                AND jsonb_typeof(summary_audit_json) = 'object'
                AND summary_audit_json ->> 'schemaVersion' = '2.0'
                AND jsonb_typeof(summary_audit_json -> 'prose') = 'string'
                AND jsonb_typeof(summary_audit_json -> 'evidenceIds') = 'array'
                AND jsonb_typeof(summary_audit_json -> 'scope') = 'object'
            )
        );
