package io.gulay.user.client;

import lombok.val;

import io.gulay.user.data.model.UserRole;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;
import org.springframework.web.util.UriComponentsBuilder;

@Component
@RequiredArgsConstructor
public class KeycloakAdminClient {
    private final RestClient.Builder restClientBuilder;

    @Value("${kozmik.keycloak.realm-url}") private String realmUrl;
    @Value("${spring.security.oauth2.client.provider.keycloak.token-uri}") private String tokenUri;
    @Value("${spring.security.oauth2.client.registration.keycloak.client-id}") private String clientId;
    @Value("${spring.security.oauth2.client.registration.keycloak.client-secret}") private String clientSecret;
    @Value("${kozmik.keycloak.action-email-client-id:kozmik-backend}") private String actionEmailClientId;
    @Value("${kozmik.keycloak.action-email-redirect-uri:http://localhost:5173}") private String actionEmailRedirectUri;
    @Value("${kozmik.keycloak.action-email-lifespan-seconds:900}") private int actionEmailLifespanSeconds;

    public List<IdentityUser> users() {
        val result = new ArrayList<IdentityUser>();
        for (int first = 0; ; first += 100) {
            val page = client().get()
                    .uri(adminUrl() + "/users?first=" + first + "&max=100")
                    .headers(headers -> headers.setBearerAuth(token()))
                    .retrieve().body(IdentityUser[].class);
            if (page == null || page.length == 0) break;
            for (val user : page) {
                if (user.username() != null && !user.username().startsWith("service-account-")) {
                    result.add(user.withRoles(roles(user.id())));
                }
            }
            if (page.length < 100) break;
        }
        return result;
    }

    public IdentityUser create(
            String username, String displayName, String email,
            Set<UserRole> desiredRoles) {
        val names = splitName(displayName);
        val response = client().post().uri(adminUrl() + "/users")
                .headers(headers -> headers.setBearerAuth(token()))
                .contentType(MediaType.APPLICATION_JSON)
                .body(Map.of(
                        "username", username,
                        "firstName", names[0],
                        "lastName", names[1],
                        "email", email,
                        "emailVerified", false,
                        "enabled", true))
                .retrieve().toBodilessEntity();
        if (response.getStatusCode() != HttpStatus.CREATED || response.getHeaders().getLocation() == null) {
            throw new IllegalStateException("Keycloak did not return the created user identifier");
        }
        val location = response.getHeaders().getLocation().getPath();
        val userId = location.substring(location.lastIndexOf('/') + 1);
        replaceRoles(userId, desiredRoles);
        return new IdentityUser(userId, username, names[0], names[1], email, true, desiredRoles);
    }

    public void sendPasswordActionEmail(String userId) {
        val uri = UriComponentsBuilder
                .fromUriString(adminUrl() + "/users/" + userId + "/execute-actions-email")
                .queryParam("client_id", actionEmailClientId)
                .queryParam("redirect_uri", actionEmailRedirectUri)
                .queryParam("lifespan", actionEmailLifespanSeconds)
                .build().encode().toUri();
        client().put()
                .uri(uri)
                .headers(headers -> headers.setBearerAuth(token()))
                .contentType(MediaType.APPLICATION_JSON)
                .body(List.of("UPDATE_PASSWORD"))
                .retrieve().toBodilessEntity();
    }

    public void update(String userId, String displayName, String email, Set<UserRole> desiredRoles) {
        val names = splitName(displayName);
        val username = email.trim().toLowerCase(java.util.Locale.ROOT);
        client().put().uri(adminUrl() + "/users/" + userId)
                .headers(headers -> headers.setBearerAuth(token()))
                .contentType(MediaType.APPLICATION_JSON)
                .body(Map.of(
                        "username", username,
                        "firstName", names[0], "lastName", names[1],
                        "email", email, "emailVerified", true))
                .retrieve().toBodilessEntity();
        replaceRoles(userId, desiredRoles);
        logout(userId);
    }

    public void enabled(String userId, boolean enabled) {
        client().put().uri(adminUrl() + "/users/" + userId)
                .headers(headers -> headers.setBearerAuth(token()))
                .contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("enabled", enabled))
                .retrieve().toBodilessEntity();
        if (!enabled) logout(userId);
    }

    public void delete(String userId) {
        try {
            client().delete().uri(adminUrl() + "/users/" + userId)
                    .headers(headers -> headers.setBearerAuth(token()))
                    .retrieve().toBodilessEntity();
        } catch (HttpClientErrorException.NotFound ignored) {
            // Delete is deliberately idempotent for crash-safe retries.
        }
    }

    private void logout(String userId) {
        try {
            client().post().uri(adminUrl() + "/users/" + userId + "/logout")
                    .headers(headers -> headers.setBearerAuth(token()))
                    .retrieve().toBodilessEntity();
        } catch (HttpClientErrorException.NotFound ignored) {
            // No active identity/session is already the intended state.
        }
    }

    private void replaceRoles(String userId, Set<UserRole> desired) {
        val current = roleRepresentations(userId).stream()
                .filter(role -> isPlatformRole(String.valueOf(role.get("name")))).toList();
        if (!current.isEmpty()) {
            client().method(HttpMethod.DELETE).uri(adminUrl() + "/users/" + userId + "/role-mappings/realm")
                    .headers(headers -> headers.setBearerAuth(token()))
                    .contentType(MediaType.APPLICATION_JSON).body(current)
                    .retrieve().toBodilessEntity();
        }
        val replacements = desired.stream().map(role -> realmRole(role.name())).toList();
        client().post().uri(adminUrl() + "/users/" + userId + "/role-mappings/realm")
                .headers(headers -> headers.setBearerAuth(token()))
                .contentType(MediaType.APPLICATION_JSON).body(replacements)
                .retrieve().toBodilessEntity();
    }

    private Set<UserRole> roles(String userId) {
        return roleRepresentations(userId).stream()
                .map(role -> String.valueOf(role.get("name")))
                .filter(this::isPlatformRole)
                .map(UserRole::valueOf)
                .collect(java.util.stream.Collectors.toUnmodifiableSet());
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> roleRepresentations(String userId) {
        val value = client().get()
                .uri(adminUrl() + "/users/" + userId + "/role-mappings/realm")
                .headers(headers -> headers.setBearerAuth(token()))
                .retrieve().body(List.class);
        return value == null ? List.of() : value;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> realmRole(String name) {
        return client().get().uri(adminUrl() + "/roles/" + name)
                .headers(headers -> headers.setBearerAuth(token()))
                .retrieve().body(Map.class);
    }

    @SuppressWarnings("unchecked")
    private String token() {
        val form = new LinkedMultiValueMap<String, String>();
        form.add("grant_type", "client_credentials");
        form.add("client_id", clientId);
        form.add("client_secret", clientSecret);
        val response = client().post().uri(tokenUri)
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(form).retrieve().body(Map.class);
        return String.valueOf(response.get("access_token"));
    }

    private RestClient client() {
        return restClientBuilder.build();
    }

    private String adminUrl() {
        return realmUrl.replace("/realms/", "/admin/realms/");
    }

    private boolean isPlatformRole(String role) {
        try { UserRole.valueOf(role); return true; }
        catch (IllegalArgumentException ignored) { return false; }
    }

    private String[] splitName(String displayName) {
        val parts = displayName.trim().split("\\s+", 2);
        return new String[] {parts[0], parts.length == 2 ? parts[1] : ""};
    }

    public record IdentityUser(
            String id, String username, String firstName, String lastName,
            String email, boolean enabled, Set<UserRole> roles) {
        public IdentityUser withRoles(Set<UserRole> value) {
            return new IdentityUser(id, username, firstName, lastName, email, enabled, value);
        }
        public String displayName() {
            return ((firstName == null ? "" : firstName) + " "
                    + (lastName == null ? "" : lastName)).trim();
        }
    }
}
