Feature: Passwordless public lab access
  Public access is opt-in and the instructor code is the sole secret.

  Scenario: Instructor creates a public workshop
    Given a public-certified execution cluster and an eligible catalog item
    When the instructor orders a public workshop with 25 seats
    Then the response contains one public URL and one code shown once
    And no plaintext code is persisted

  Scenario: Concurrent participants claim unique seats
    Given an unexpired public workshop with 25 available seats
    When 25 participants submit the shared code simultaneously
    Then every participant receives exactly one distinct seat

  Scenario: Participant recovers a seat and adds another lab
    Given a participant has claimed one workshop seat
    When the normalized email and code are submitted again
    Then the same seat is recovered
    When the same email submits a second order code
    Then the same stable identity receives a second entitlement

  Scenario: Rotation immediately denies existing access
    Given a participant has an active entitlement
    When the instructor rotates the order code
    Then authorization for that order is denied
    And unrelated order entitlements remain active
    When the participant submits the replacement code
    Then the existing seat is restored

  Scenario: Expiry and reclaim leave no residue
    Given a participant has access to Showroom workspace and OpenShift Console
    When the order TTL expires or the instructor reclaims it
    Then authorization is immediately denied
    And cleanup removes routes namespaces RoleBindings applications entitlements and inactive identities
