package io.gulay.execution.data.service;

import java.text.Normalizer;
import java.util.Locale;
import java.util.regex.Pattern;

final class SummaryPreference {
    private static final Pattern EXCLUDED = Pattern.compile(
            "(?:\\b(?:exclude|omit|skip|remove|disable)\\s+(?:the\\s+)?"
                    + "(?:(?:result|execution|business)\\s+)?summary\\b)"
                    + "|(?:\\bdo\\s+not\\s+(?:include|generate|add|provide|show)\\s+"
                    + "(?:a\\s+|the\\s+)?(?:(?:result|execution|business)\\s+)?summary\\b)"
                    + "|(?:\\bwithout\\s+(?:a\\s+|the\\s+)?"
                    + "(?:(?:result|execution|business)\\s+)?summary\\b)"
                    + "|(?:\\bno\\s+(?:(?:result|execution|business)\\s+)?summary\\b)"
                    + "|(?:\\bözet(?:i)?\\s+(?:dahil\\s+etme|ekleme|oluşturma|üretme|"
                    + "gösterme|sunma|istemiyorum|istemem)\\b)"
                    + "|(?:\\bözet\\s+(?:dahil\\s+olmasın|olmasın)\\b)"
                    + "|(?:\\bözetsiz\\b)",
            Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE);

    private SummaryPreference() {
    }

    static boolean include(String request) {
        if (request == null || request.isBlank()) {
            return true;
        }
        var normalized = Normalizer.normalize(request, Normalizer.Form.NFKC)
                .toLowerCase(Locale.ROOT);
        return !EXCLUDED.matcher(normalized).find();
    }
}
