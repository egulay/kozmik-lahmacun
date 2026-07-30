package io.gulay.execution;

import lombok.val;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import tools.jackson.databind.ObjectMapper;
import io.gulay.execution.messaging.KafkaMessageSigner;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

class KafkaMessageSignerTest {
    @Test
    void signedEnvelopeRoundTripsAndRejectsTampering() {
        val signer = new KafkaMessageSigner(new ObjectMapper());
        ReflectionTestUtils.setField(signer, "signingKey", "k".repeat(64));
        val payload = "{\"schemaVersion\":\"1.0\",\"eventId\":\"safe\"}";
        val signed = signer.wrap(payload);

        assertThat(signer.unwrap(signed)).isEqualTo(payload);
        assertThatThrownBy(() -> signer.unwrap(
                signed.substring(0, signed.length() - 2) + "x}"))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
