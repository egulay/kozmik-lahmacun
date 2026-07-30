package io.gulay.execution.messaging;

import io.gulay.execution.data.model.ExecutionCommandOutboxModel;
import io.gulay.execution.data.repository.ExecutionCommandOutboxRepository;

import java.time.Clock;
import java.time.Instant;

import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
@ConditionalOnProperty(name = "kozmik.kafka.outbox-enabled", havingValue = "true",
        matchIfMissing = true)
@RequiredArgsConstructor
public class ExecutionCommandPublisher {
    private final ExecutionCommandOutboxRepository repository;
    private final KafkaTemplate<String, String> kafka;
    private final KafkaMessageSigner signer;
    private final Clock clock;
    @Value("${kozmik.kafka.command-topic:execution.commands.v1}")
    private String topic;
    @Value("${kozmik.kafka.publish-max-attempts:5}")
    private int maxAttempts;

    @Scheduled(fixedDelayString = "${kozmik.kafka.outbox-poll-ms:500}")
    @Transactional
    public void publishPending() {
        repository.findTop50ByPublishedAtIsNullAndAttemptCountLessThanOrderByCreatedAt(maxAttempts)
                .forEach(this::publish);
    }

    private void publish(ExecutionCommandOutboxModel item) {
        try {
            kafka.send(topic, item.getExecution().getId().toString(),
                            signer.wrap(item.getPayloadJson()))
                    .get(10, java.util.concurrent.TimeUnit.SECONDS);
            item.published(Instant.now(clock));
        } catch (Exception exception) {
            item.failed("KAFKA_COMMAND_PUBLISH_FAILED");
        }
    }
}
