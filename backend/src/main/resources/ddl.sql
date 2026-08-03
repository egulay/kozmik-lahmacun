\set ON_ERROR_STOP on

-- Destructive local-demo bootstrap only. Flyway migrations remain the canonical
-- schema definition; this script replays them into a completely clean schema.
DROP SCHEMA IF EXISTS kozmik_lahmacun CASCADE;
CREATE SCHEMA kozmik_lahmacun;
GRANT ALL ON SCHEMA kozmik_lahmacun TO CURRENT_USER;
SET search_path TO kozmik_lahmacun;

\ir db/migration/V1__control_plane_foundation.sql
\ir db/migration/V2__entity_schema_management.sql
\ir db/migration/V3__chat_subsystem.sql
\ir db/migration/V4__structured_report_planning.sql
\ir db/migration/V5__kafka_execution_backbone.sql
\ir db/migration/V6__trusted_report_results.sql
\ir db/migration/V7__event_driven_import_jobs.sql
\ir db/migration/V8__result_summary_status.sql
\ir db/migration/V9__lifecycle_hardening.sql
\ir db/migration/V10__execution_dataset_binding.sql
\ir db/migration/V11__continuous_ingestion_streams.sql
\ir db/migration/V12__execution_failure_explanations.sql
\ir db/migration/V13__durable_async_execution_planning.sql
\ir db/migration/V14__durable_execution_deletion.sql
\ir db/migration/V15__user_management.sql
\ir db/migration/V16__remove_runtime_settings_and_restart.sql
\ir db/migration/V17__ingestion_activity_status.sql
\ir db/migration/V18__single_entity_schema_contract.sql
\ir db/migration/V19__chat_thread_cascade_cleanup.sql
\ir db/migration/V20__localized_entity_metadata.sql
\ir db/migration/V21__hard_delete_retention.sql
\ir db/migration/V22__governed_categorical_vocabulary.sql
\ir db/migration/V23__unbounded_management_summary.sql
\ir db/migration/V24__management_evidence_audit.sql
\ir db/migration/V25__management_summary_draft_audit.sql
\ir db/migration/V26__rename_management_summary_audit.sql
\ir db/migration/V27__simplify_management_summary_audit.sql
\ir db/migration/V28__rename_result_summary.sql
\ir db/migration/V29__simplify_result_summary.sql
\ir db/migration/V30__optional_result_summary.sql
\ir db/migration/V31__allow_skipped_result_summary_status.sql
