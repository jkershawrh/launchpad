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

  Scenario: Multiple orders share one trusted public origin
    Given two active public workshops use the same approved hostname
    When a participant opens each order-specific path
    Then each path resolves only its persisted order and seat
    And no raw execution-cluster hostname is returned to the browser

  Scenario: Showroom tools remain on the entitled order path
    Given a participant has an active seat with RAG terminal and Console tools
    When Showroom loads its generated UI configuration
    Then every private tool uses an order-scoped gateway-relative path
    And undeclared private cluster tabs are removed
    And terminal WebSockets retain the same order context

  Scenario: Participant-created tool is not ready
    Given the lab guide declares a tool that the participant deploys later
    When the participant opens its Showroom tab before the Route is ready
    Then the gateway displays a retryable not-ready panel
    And the browser does not navigate to an untrusted cluster Route

  Scenario: Gateway verifies private ingress certificates
    Given the selected cluster ingress CA is installed in the gateway trust bundle
    When the gateway connects to Showroom Console or an operator Route
    Then TLS hostname and chain verification succeed
    And a missing or invalid cluster CA fails closed
