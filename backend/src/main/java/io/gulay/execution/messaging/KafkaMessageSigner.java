package io.gulay.execution.messaging;

import lombok.val;

import tools.jackson.databind.ObjectMapper;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
@RequiredArgsConstructor
public class KafkaMessageSigner {
    private final ObjectMapper mapper;

    @Value("${kozmik.security.kafka-message-signing-key:}")
    private String signingKey;

    public String wrap(String payload) {
        requireKey();
        try {
            val encoded = Base64.getUrlEncoder().withoutPadding()
                    .encodeToString(payload.getBytes(StandardCharsets.UTF_8));
            return mapper.writeValueAsString(new SignedEnvelope("1.0", encoded, sign(encoded)));
        } catch (Exception exception) {
            throw new IllegalStateException("Unable to sign Kafka message", exception);
        }
    }

    public String unwrap(String envelope) {
        requireKey();
        try {
            val signed = mapper.readValue(envelope, SignedEnvelope.class);
            if (!"1.0".equals(signed.schemaVersion())
                    || !MessageDigest.isEqual(
                    sign(signed.payload()).getBytes(StandardCharsets.US_ASCII),
                    signed.signature().getBytes(StandardCharsets.US_ASCII))) {
                throw new IllegalArgumentException("Kafka message signature is invalid");
            }
            return new String(Base64.getUrlDecoder().decode(signed.payload()),
                    StandardCharsets.UTF_8);
        } catch (IllegalArgumentException exception) {
            throw exception;
        } catch (Exception exception) {
            throw new IllegalArgumentException("Kafka signed envelope is invalid", exception);
        }
    }

    private String sign(String encodedPayload) throws Exception {
        val mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(
                signingKey.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
        return Base64.getUrlEncoder().withoutPadding().encodeToString(
                mac.doFinal(encodedPayload.getBytes(StandardCharsets.US_ASCII)));
    }

    private void requireKey() {
        if (signingKey == null || signingKey.length() < 32) {
            throw new IllegalStateException("Kafka message signing key is not configured");
        }
    }

    private record SignedEnvelope(String schemaVersion, String payload, String signature) {
    }
}
