package io.gulay.execution.data.service;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class SummaryPreferenceTest {
    @Test
    void includesSummaryByDefaultAndForExplicitRequests() {
        assertThat(SummaryPreference.include("Show regional sales")).isTrue();
        assertThat(SummaryPreference.include("Include a summary")).isTrue();
        assertThat(SummaryPreference.include("Özeti dahil et")).isTrue();
    }

    @Test
    void excludesSummaryForEnglishAndTurkishNegativeRequests() {
        assertThat(SummaryPreference.include("Show regional sales without a summary")).isFalse();
        assertThat(SummaryPreference.include("Do not include the result summary")).isFalse();
        assertThat(SummaryPreference.include("Özeti dahil etme")).isFalse();
        assertThat(SummaryPreference.include("Özet olmasın")).isFalse();
        assertThat(SummaryPreference.include("Özetsiz rapor hazırla")).isFalse();
    }
}
