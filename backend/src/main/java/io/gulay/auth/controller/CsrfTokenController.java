package io.gulay.auth.controller;

import io.gulay.auth.dto.CsrfTokenResponseDto;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/auth")
public class CsrfTokenController {

    @GetMapping("/csrf")
    public CsrfTokenResponseDto csrfToken(@RequestAttribute("_csrf") CsrfToken csrfToken) {
        return new CsrfTokenResponseDto(
                csrfToken.getHeaderName(), csrfToken.getParameterName(), csrfToken.getToken());
    }
}
