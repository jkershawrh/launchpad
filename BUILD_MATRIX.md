# Build Red/Green Matrix

> Generated: 2026-05-18 | All Phases Complete

## Platform Gates

| # | Build Stage | Status | Evidence |
|---|---|---|---|
| 1 | Tenant Model | GREEN | test_tenant.py (4) |
| 2 | Catalog Model | GREEN | test_catalog_item.py (5) |
| 3 | Lab Request Model | GREEN | test_lab_request.py (5) |
| 4 | Lab Session Lifecycle | GREEN | test_lifecycle.py (8) |
| 5 | Adapter Interfaces | GREEN | interfaces.py + 9 mock adapters |
| 6 | Mock Provisioning | GREEN | test_e2e_provisioning.py (5) |
| 7 | Validation | GREEN | test_lifecycle.py + test_adapters.py |
| 8 | Handoff Package | GREEN | test_reports.py + test_api.py |
| 9 | Showback | GREEN | test_adapters.py + test_api.py |
| 10 | Branding | GREEN | test_branding_profile.py + test_api.py |
| 11 | Repeatability Report | GREEN | test_reports.py + test_api.py |
| 12 | API | GREEN | test_api.py (27) |
| 13 | UI | GREEN | 2 apps, both build clean |
| 14 | Regression | GREEN | 125/125 passing |

## Launch Lab Workflow Rubric

Every step has a GREEN (success) and RED (failure) test.

| # | Workflow Step | GREEN | RED | Status |
|---|---|---|---|---|
| 1 | Submit request with valid catalog item | PASS | PASS | GREEN |
| 2 | Constraint evaluation | PASS | PASS | GREEN |
| 3 | Request status set correctly | PASS | PASS | GREEN |
| 4 | Provision requires accepted request | PASS | PASS | GREEN |
| 5 | Provision finds request by ID | PASS | PASS | GREEN |
| 6 | Pool capacity check + reserve | PASS | PASS | GREEN |
| 7 | Provisioning plan created | PASS | PASS | GREEN |
| 8 | Provisioning executes | PASS | PASS | GREEN |
| 9 | Session created with correct state | PASS | PASS | GREEN |
| 10 | REQUESTED → PROVISIONING | PASS | PASS | GREEN |
| 11 | PROVISIONING → VALIDATING | PASS | PASS | GREEN |
| 12 | Validate finds session by ID | PASS | PASS | GREEN |
| 13 | Validation runs checks | PASS | PASS | GREEN |
| 14 | VALIDATING → READY (all pass) | PASS | PASS | GREEN |
| 15 | VALIDATING → VALIDATION_FAILED | PASS | PASS | GREEN |
| 16 | Handoff generated | PASS | PASS | GREEN |
| 17 | Showback record created | PASS | PASS | GREEN |
| 18 | Repeatability score | PASS | PASS | GREEN |
| 19 | API: full workflow HTTP | PASS | PASS | GREEN |
| 20 | API: bad request HTTP | PASS | PASS | GREEN |

## Summary

- **Total tests:** 125 passing
- **Workflow rubric:** 20/20 steps GREEN (36 unit + 3 API tests)
- **Platform gates:** 14/14 GREEN
- **Frontend apps:** 2 (partner portal + admin), both build clean
