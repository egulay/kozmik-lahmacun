package io.gulay.execution.data.model;


public enum ExecutionStatus {
    PLANNING, VALIDATED, QUEUED, RUNNING, SUCCEEDED, FAILED, CANCELLED, TIMED_OUT;

    public boolean terminal() {
        return this == SUCCEEDED || this == FAILED || this == CANCELLED || this == TIMED_OUT;
    }
}
