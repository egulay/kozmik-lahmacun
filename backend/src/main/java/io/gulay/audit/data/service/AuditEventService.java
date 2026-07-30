package io.gulay.audit.data.service;

import io.gulay.audit.data.model.AuditEventModel;
import io.gulay.audit.data.model.AuditOutcome;
import io.gulay.audit.data.repository.AuditEventRepository;
import io.gulay.user.data.model.AppUserReferenceModel;

import java.time.Clock;
import java.time.Instant;
import java.util.UUID;

import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
public class AuditEventService {

    private final AuditEventRepository repository;
    private final Clock clock;

    @Transactional
    public AuditEventModel record(
            String eventType,
            AppUserReferenceModel actor,
            String subjectType,
            String subjectId,
            String correlationId,
            AuditOutcome outcome,
            String detailCode) {
        return repository.save(AuditEventModel.builder()
                .id(UUID.randomUUID())
                .eventType(eventType)
                .actor(actor)
                .subjectType(subjectType)
                .subjectId(subjectId)
                .correlationId(correlationId)
                .outcome(outcome)
                .detailCode(detailCode)
                .occurredAt(Instant.now(clock))
                .build());
    }

}
