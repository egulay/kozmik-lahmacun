package io.gulay.security;

import lombok.val;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.HttpSessionOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.oauth2.client.web.OAuth2LoginAuthenticationFilter;
import org.springframework.security.oauth2.client.oidc.web.logout.OidcClientInitiatedLogoutSuccessHandler;
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;

@Configuration
@EnableWebSecurity
@RequiredArgsConstructor
@Slf4j
public class SecurityConfiguration {

    private final KeycloakOidcUserService oidcUserService;
    private final InternalApiKeyFilter internalApiKeyFilter;

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository authorizedClients,
            OAuth2TokenRefreshFilter tokenRefreshFilter,
            RequestRateLimitFilter rateLimitFilter)
            throws Exception {
        val csrfRepository = new HttpSessionCsrfTokenRepository();
        csrfRepository.setHeaderName("X-CSRF-TOKEN");

        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/", "/error", "/oauth2/**", "/login/**")
                        .permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/auth/csrf")
                        .permitAll()
                        .requestMatchers(
                                "/actuator/health",
                                "/actuator/health/liveness",
                                "/actuator/health/readiness")
                        .permitAll()
                        .requestMatchers("/actuator/**")
                        .hasRole(PlatformRole.ADMIN.name())
                        .requestMatchers("/api/admin/**")
                        .hasRole(PlatformRole.ADMIN.name())
                        .requestMatchers("/internal/v1/**")
                        .hasRole("INTERNAL_SERVICE")
                        .requestMatchers(HttpMethod.GET, "/api/auth/me")
                        .authenticated()
                        .requestMatchers("/api/**")
                        .authenticated()
                        .anyRequest()
                        .denyAll())
                .exceptionHandling(exceptions -> exceptions.defaultAuthenticationEntryPointFor(
                                new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED),
                                PathPatternRequestMatcher.withDefaults().matcher("/api/**"))
                        .defaultAuthenticationEntryPointFor(
                                new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED),
                                PathPatternRequestMatcher.withDefaults().matcher("/internal/**")))
                .addFilterBefore(internalApiKeyFilter, UsernamePasswordAuthenticationFilter.class)
                .addFilterAfter(tokenRefreshFilter, OAuth2LoginAuthenticationFilter.class)
                .addFilterAfter(rateLimitFilter, OAuth2TokenRefreshFilter.class)
                .csrf(csrf -> csrf
                        .csrfTokenRepository(csrfRepository)
                        .ignoringRequestMatchers(
                                PathPatternRequestMatcher.withDefaults()
                                        .matcher("/internal/**")))
                .oauth2Login(oauth -> oauth
                        .authorizedClientRepository(authorizedClients)
                        .successHandler((request, response, authentication) -> {
                            var selectedLocale = "en";
                            val cookies = request.getCookies();
                            if (cookies != null) {
                                for (val cookie : cookies) {
                                    if ("kozmik-login-locale".equals(cookie.getName())
                                            && "tr".equalsIgnoreCase(cookie.getValue())) {
                                        selectedLocale = "tr";
                                        break;
                                    }
                                }
                            }
                            log.info("oidc_login_success selectedLocale={}", selectedLocale);
                            response.sendRedirect("/?locale=" + selectedLocale);
                        })
                        .userInfoEndpoint(
                                userInfo -> userInfo.oidcUserService(oidcUserService::loadUser)))
                .logout(logout -> logout
                        .logoutUrl("/api/auth/logout")
                        .logoutSuccessHandler(oidcLogoutSuccessHandler(registrations))
                        .invalidateHttpSession(true)
                        .clearAuthentication(true)
                        .deleteCookies("KOZMIK_SESSION"))
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
                        .sessionFixation(fixation -> fixation.changeSessionId())
                        .maximumSessions(1))
                .build();
    }

    @Bean
    OAuth2AuthorizedClientRepository authorizedClientRepository() {
        return new HttpSessionOAuth2AuthorizedClientRepository();
    }

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository authorizedClients) {
        val manager = new DefaultOAuth2AuthorizedClientManager(registrations, authorizedClients);
        manager.setAuthorizedClientProvider(OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .build());
        return manager;
    }

    @Bean
    RoleHierarchy roleHierarchy() {
        return RoleHierarchyImpl.fromHierarchy(
                "ROLE_ADMIN > ROLE_SCIENTIST\nROLE_SCIENTIST > ROLE_REPORTER");
    }

    @Bean
    static org.springframework.security.config.core.GrantedAuthorityDefaults grantedAuthorityDefaults() {
        return new org.springframework.security.config.core.GrantedAuthorityDefaults("ROLE_");
    }

    private OidcClientInitiatedLogoutSuccessHandler oidcLogoutSuccessHandler(
            ClientRegistrationRepository registrations) {
        val handler = new OidcClientInitiatedLogoutSuccessHandler(registrations);
        handler.setPostLogoutRedirectUri("{baseUrl}/");
        return handler;
    }
}
