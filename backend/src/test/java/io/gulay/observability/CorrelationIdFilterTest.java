package io.gulay.observability;

import lombok.val;

import jakarta.servlet.ServletException;
import java.io.IOException;
import org.junit.jupiter.api.Test;
import org.slf4j.MDC;
import org.springframework.mock.web.MockFilterChain;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import static org.assertj.core.api.Assertions.assertThat;

class CorrelationIdFilterTest {

    private final CorrelationIdFilter filter = new CorrelationIdFilter();

    @Test
    void preservesSafeCallerCorrelationId() throws ServletException, IOException {
        val request = new MockHttpServletRequest();
        request.addHeader(CorrelationIdFilter.HEADER, "request-123");
        val response = new MockHttpServletResponse();

        filter.doFilter(request, response, new MockFilterChain());

        assertThat(response.getHeader(CorrelationIdFilter.HEADER)).isEqualTo("request-123");
        assertThat(MDC.get("correlationId")).isNull();
    }

    @Test
    void replacesUnsafeCorrelationId() throws ServletException, IOException {
        val request = new MockHttpServletRequest();
        request.addHeader(CorrelationIdFilter.HEADER, "unsafe value\n");
        val response = new MockHttpServletResponse();

        filter.doFilter(request, response, new MockFilterChain());

        assertThat(response.getHeader(CorrelationIdFilter.HEADER))
                .matches("[0-9a-f]{8}-[0-9a-f-]{27}");
    }
}
