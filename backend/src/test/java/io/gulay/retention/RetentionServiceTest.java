package io.gulay.retention;

import io.gulay.audit.data.model.AuditOutcome;
import io.gulay.audit.data.service.AuditEventService;
import io.gulay.execution.messaging.KafkaMessageSigner;
import io.gulay.retention.data.repository.RetentionPurgeRepository;
import io.gulay.retention.data.service.RetentionService;
import lombok.val;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.transaction.support.TransactionTemplate;
import tools.jackson.databind.ObjectMapper;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class RetentionServiceTest {

    @Test
    void midnightRetentionPurgesEverySoftDeleteDomainInBatches() {
        val audit = mock(AuditEventService.class);
        val purge = mock(RetentionPurgeRepository.class);
        val clock = Clock.fixed(Instant.parse("2026-07-30T00:00:00Z"), ZoneOffset.UTC);
        @SuppressWarnings("unchecked")
        val kafka = (KafkaTemplate<String, String>) mock(KafkaTemplate.class);
        val service = new RetentionService(
                mock(JdbcTemplate.class),
                audit,
                clock,
                kafka,
                mock(KafkaMessageSigner.class),
                mock(ObjectMapper.class),
                purge,
                mock(TransactionTemplate.class));
        ReflectionTestUtils.setField(service, "hardDeleteDays", 30L);
        val cutoff = Instant.parse("2026-06-30T00:00:00Z");

        when(purge.purgeConfirmedDeletedArtifacts(cutoff)).thenReturn(100, 2, 0);
        when(purge.purgeSoftDeletedExecutions(cutoff)).thenReturn(3, 0);
        when(purge.purgeSoftDeletedUsers(cutoff)).thenReturn(1, 0);

        service.hardDeleteSoftDeletedData();

        verify(purge, times(3)).purgeConfirmedDeletedArtifacts(cutoff);
        verify(purge, times(2)).purgeSoftDeletedExecutions(cutoff);
        verify(purge, times(2)).purgeSoftDeletedUsers(cutoff);
        verify(audit).record(
                eq("HARD_DELETE_RETENTION_RUN"),
                isNull(),
                eq("RETENTION"),
                org.mockito.ArgumentMatchers.anyString(),
                org.mockito.ArgumentMatchers.anyString(),
                eq(AuditOutcome.SUCCEEDED),
                eq("HARD_DELETE_RETENTION_COMPLETED"));
    }
}
