package io.gulay.security;

import lombok.val;

import io.gulay.user.data.service.AppUserReferenceService;

import java.util.LinkedHashSet;

import lombok.RequiredArgsConstructor;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.core.oidc.user.DefaultOidcUser;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class KeycloakOidcUserService {

    private final AppUserReferenceService userReferenceService;
    private final JwtDecoder jwtDecoder;

    public OidcUser loadUser(OidcUserRequest request) {
        val oidcUser = new OidcUserService().loadUser(request);
        val authorities = new LinkedHashSet<GrantedAuthority>(oidcUser.getAuthorities());
        authorities.addAll(KeycloakRoleAuthorities.extract(oidcUser.getClaims()));
        authorities.addAll(KeycloakRoleAuthorities.extract(
                jwtDecoder.decode(request.getAccessToken().getTokenValue()).getClaims()));

        userReferenceService.synchronize(
                oidcUser.getSubject(), oidcUser.getFullName(), oidcUser.getEmail());

        val userNameAttribute = request.getClientRegistration()
                .getProviderDetails()
                .getUserInfoEndpoint()
                .getUserNameAttributeName();
        return userNameAttribute == null || userNameAttribute.isBlank()
                ? new DefaultOidcUser(authorities, oidcUser.getIdToken(), oidcUser.getUserInfo())
                : new DefaultOidcUser(
                authorities,
                oidcUser.getIdToken(),
                oidcUser.getUserInfo(),
                userNameAttribute);
    }
}
