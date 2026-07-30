ALTER TABLE ingestion_stream
    DROP CONSTRAINT IF EXISTS ingestion_stream_status_check;

ALTER TABLE ingestion_stream
    ADD CONSTRAINT ingestion_stream_status_check
        CHECK (status IN (
            'ACTIVE', 'INGESTING', 'COMPLETED', 'DRAINING', 'STOPPED', 'FAILED'
        ));

UPDATE ingestion_stream
SET status = 'COMPLETED'
WHERE status = 'ACTIVE'
  AND last_sequence IS NOT NULL
  AND last_offset IS NOT NULL;
