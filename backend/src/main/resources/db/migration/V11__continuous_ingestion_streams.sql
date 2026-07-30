CREATE TABLE ingestion_stream (
    id UUID PRIMARY KEY,
    entity_id UUID NOT NULL REFERENCES business_entity(id),
    schema_version_id UUID REFERENCES entity_schema_version(id),
    source_id VARCHAR(120) NOT NULL,
    topic VARCHAR(200) NOT NULL,
    status VARCHAR(40) NOT NULL CHECK (status IN ('ACTIVE', 'DRAINING', 'STOPPED', 'FAILED')),
    cumulative_rows BIGINT NOT NULL DEFAULT 0 CHECK (cumulative_rows >= 0),
    last_sequence BIGINT,
    last_chunk_id UUID,
    last_partition INTEGER,
    last_offset BIGINT,
    last_watermark TIMESTAMP WITH TIME ZONE,
    last_error_code VARCHAR(120),
    started_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    stopped_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE ingestion_stream_batch (
    chunk_id UUID PRIMARY KEY,
    stream_id UUID NOT NULL REFERENCES ingestion_stream(id),
    sequence_number BIGINT NOT NULL,
    kafka_partition INTEGER NOT NULL,
    first_offset BIGINT NOT NULL,
    last_offset BIGINT NOT NULL,
    row_count BIGINT CHECK (row_count IS NULL OR row_count >= 0),
    status VARCHAR(40) NOT NULL,
    refined_bucket VARCHAR(120),
    refined_object_key VARCHAR(1000),
    produced_at TIMESTAMP WITH TIME ZONE NOT NULL,
    completed_at TIMESTAMP WITH TIME ZONE,
    error_code VARCHAR(120),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    UNIQUE (stream_id, sequence_number),
    UNIQUE (stream_id, kafka_partition, first_offset)
);

CREATE TABLE ingestion_stream_event (
    event_id UUID PRIMARY KEY,
    stream_id UUID NOT NULL REFERENCES ingestion_stream(id),
    chunk_id UUID NOT NULL,
    stage VARCHAR(40) NOT NULL,
    message_code VARCHAR(120) NOT NULL,
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE execution_stream_binding (
    execution_id UUID PRIMARY KEY REFERENCES execution_request(id),
    stream_id UUID NOT NULL REFERENCES ingestion_stream(id),
    through_sequence BIGINT NOT NULL,
    through_offset BIGINT NOT NULL,
    snapshot_row_count BIGINT NOT NULL CHECK (snapshot_row_count >= 0),
    resolved_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX idx_ingestion_stream_entity_updated
    ON ingestion_stream(entity_id, updated_at DESC);
CREATE INDEX idx_ingestion_stream_batch_stream_sequence
    ON ingestion_stream_batch(stream_id, sequence_number);
