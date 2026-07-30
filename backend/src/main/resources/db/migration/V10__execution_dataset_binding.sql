CREATE TABLE execution_dataset_binding (
    execution_id UUID PRIMARY KEY REFERENCES execution_request(id),
    import_job_id UUID NOT NULL REFERENCES import_job(id),
    resolved_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX idx_execution_dataset_binding_import
    ON execution_dataset_binding(import_job_id);
