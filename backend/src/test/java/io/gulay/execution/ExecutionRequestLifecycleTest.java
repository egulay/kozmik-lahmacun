package io.gulay.execution;

import lombok.val;

import io.gulay.execution.data.model.ExecutionRequestModel;
import io.gulay.execution.data.model.ExecutionStatus;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class ExecutionRequestLifecycleTest {
    @Test
    void terminalStateCannotBeOverwrittenAndCancellationIsIdempotent() {
        val execution = ExecutionRequestModel.builder().id(UUID.randomUUID())
                .status(ExecutionStatus.RUNNING).build();
        val now = Instant.now();
        assertThat(execution.requestCancellation(now)).isTrue();
        assertThat(execution.requestCancellation(now.plusSeconds(1))).isFalse();
        assertThat(execution.applyStatus(ExecutionStatus.CANCELLED, now.plusSeconds(2))).isTrue();
        assertThat(execution.applyStatus(ExecutionStatus.SUCCEEDED, now.plusSeconds(3))).isFalse();
        assertThat(execution.getStatus()).isEqualTo(ExecutionStatus.CANCELLED);
        assertThat(execution.getCompletedAt()).isEqualTo(now.plusSeconds(2));
    }
}
