package io.gulay.user.controller;

import io.gulay.user.data.service.UserManagementService;
import io.gulay.user.dto.UserManagementDtos;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/account")
@RequiredArgsConstructor
public class AccountController {
    private final UserManagementService service;

    @PostMapping("/password-change")
    UserManagementDtos.PasswordActionResponse requestPasswordChange(
            @AuthenticationPrincipal OidcUser actor) {
        return service.requestOwnPasswordChange(actor.getSubject());
    }
}
