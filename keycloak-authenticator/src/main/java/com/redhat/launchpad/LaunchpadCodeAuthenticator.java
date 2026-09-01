package com.redhat.launchpad;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.ws.rs.core.MultivaluedMap;
import jakarta.ws.rs.core.Response;
import org.keycloak.authentication.AuthenticationFlowContext;
import org.keycloak.authentication.AuthenticationFlowError;
import org.keycloak.authentication.Authenticator;
import org.keycloak.models.KeycloakSession;
import org.keycloak.models.RealmModel;
import org.keycloak.models.UserModel;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public final class LaunchpadCodeAuthenticator implements Authenticator {
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final HttpClient HTTP = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build();

    @Override public void authenticate(AuthenticationFlowContext context) {
        String order = context.getUriInfo().getQueryParameters().getFirst("order");
        if (order == null || order.isBlank()) {
            order = resolveOrder(context.getUriInfo().getQueryParameters().getFirst("redirect_uri"));
        }
        context.form().setAttribute("orderId", order == null ? "" : order);
        context.challenge(context.form().createForm("launchpad-code.ftl"));
    }

    @Override public void action(AuthenticationFlowContext context) {
        MultivaluedMap<String, String> form = context.getHttpRequest().getDecodedFormParameters();
        String email = value(form, "email");
        String code = value(form, "code");
        String order = value(form, "order_id");
        if (email.isBlank() || code.isBlank() || order.isBlank()) { deny(context); return; }
        try {
            String backend = required("LAUNCHPAD_ACCESS_VALIDATION_URL");
            String brokerKey = required("ACCESS_BROKER_KEY");
            String payload = JSON.createObjectNode().put("order_id", order).put("email", email).put("code", code).toString();
            HttpRequest request = HttpRequest.newBuilder(URI.create(backend))
                .timeout(Duration.ofSeconds(8)).header("Content-Type", "application/json")
                .header("X-Access-Broker-Key", brokerKey)
                .POST(HttpRequest.BodyPublishers.ofString(payload, StandardCharsets.UTF_8)).build();
            HttpResponse<String> response = HTTP.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() != 200) { deny(context); return; }
            JsonNode result = JSON.readTree(response.body());
            String username = result.path("preferred_username").asText();
            String subject = result.path("subject").asText();
            if (username.isBlank() || subject.isBlank()) { deny(context); return; }
            RealmModel realm = context.getRealm();
            UserModel user = context.getSession().users().getUserByUsername(realm, username);
            if (user == null) user = context.getSession().users().addUser(realm, username);
            user.setEnabled(true);
            user.setEmail(email.strip().toLowerCase());
            user.setSingleAttribute("launchpad_participant_id", subject);
            user.setSingleAttribute("launchpad_order_id", order);
            context.setUser(user);
            context.success();
        } catch (Exception ignored) { deny(context); }
    }

    private static String value(MultivaluedMap<String, String> form, String key) {
        String value = form.getFirst(key); return value == null ? "" : value.strip();
    }
    private static String required(String name) {
        String value = System.getenv(name); if (value == null || value.isBlank()) throw new IllegalStateException(name); return value;
    }
    private static String resolveOrder(String redirectUri) {
        if (redirectUri == null || redirectUri.isBlank()) return "";
        try {
            String host = URI.create(redirectUri).getHost();
            String validation = required("LAUNCHPAD_ACCESS_VALIDATION_URL");
            String lookup = validation.substring(0, validation.lastIndexOf('/')) + "/order-by-host?host=" + java.net.URLEncoder.encode(host, StandardCharsets.UTF_8);
            HttpRequest request = HttpRequest.newBuilder(URI.create(lookup)).timeout(Duration.ofSeconds(5))
                .header("X-Access-Broker-Key", required("ACCESS_BROKER_KEY")).GET().build();
            HttpResponse<String> response = HTTP.send(request, HttpResponse.BodyHandlers.ofString());
            return response.statusCode() == 200 ? JSON.readTree(response.body()).path("order_id").asText("") : "";
        } catch (Exception ignored) { return ""; }
    }
    private static void deny(AuthenticationFlowContext context) {
        Response challenge = context.form().setError("Access request cannot be completed.").createForm("launchpad-code.ftl");
        context.failureChallenge(AuthenticationFlowError.INVALID_CREDENTIALS, challenge);
    }
    @Override public boolean requiresUser() { return false; }
    @Override public boolean configuredFor(KeycloakSession session, RealmModel realm, UserModel user) { return true; }
    @Override public void setRequiredActions(KeycloakSession session, RealmModel realm, UserModel user) {}
    @Override public void close() {}
}
