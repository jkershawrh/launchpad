package com.redhat.launchpad;

import org.keycloak.Config;
import org.keycloak.authentication.Authenticator;
import org.keycloak.authentication.AuthenticatorFactory;
import org.keycloak.models.AuthenticationExecutionModel;
import org.keycloak.models.KeycloakSession;
import org.keycloak.models.KeycloakSessionFactory;
import org.keycloak.provider.ProviderConfigProperty;

import java.util.List;

public final class LaunchpadCodeAuthenticatorFactory implements AuthenticatorFactory {
    public static final String ID = "launchpad-order-code";
    private static final Authenticator INSTANCE = new LaunchpadCodeAuthenticator();
    @Override public String getId() { return ID; }
    @Override public String getDisplayType() { return "Launchpad email + order code"; }
    @Override public String getReferenceCategory() { return "passwordless"; }
    @Override public boolean isConfigurable() { return false; }
    @Override public AuthenticationExecutionModel.Requirement[] getRequirementChoices() { return new AuthenticationExecutionModel.Requirement[]{AuthenticationExecutionModel.Requirement.REQUIRED, AuthenticationExecutionModel.Requirement.DISABLED}; }
    @Override public boolean isUserSetupAllowed() { return false; }
    @Override public String getHelpText() { return "Validates an unverified email label and instructor order code through Launchpad."; }
    @Override public List<ProviderConfigProperty> getConfigProperties() { return List.of(); }
    @Override public Authenticator create(KeycloakSession session) { return INSTANCE; }
    @Override public void init(Config.Scope config) {}
    @Override public void postInit(KeycloakSessionFactory factory) {}
    @Override public void close() {}
}
