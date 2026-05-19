#!/usr/bin/env python3
"""
Partner AI Launchpad CLI

Usage:
  launchpad validate-catalog
  launchpad list-catalog
  launchpad create-tenant <file>
  launchpad request-lab <file>
  launchpad provision-lab <request_id>
  launchpad validate-lab <session_id>
  launchpad handoff <session_id>
  launchpad showback <session_id>
  launchpad repeatability-report <session_id>
  launchpad build-report
"""
from __future__ import annotations

import json
import sys

from app.adapters.mock.catalog import MockCatalogAdapter
from app.domain.enums import CatalogCategory, CatalogStatus, Persistence
from app.domain.models import LabRequest, Tenant
from app.services.provisioning import ProvisioningService


def validate_catalog():
    catalog = MockCatalogAdapter()
    items = catalog.list_items()
    errors = 0
    for item in items:
        valid = catalog.validate_item(item.catalog_item_id)
        status = "OK" if valid else "INVALID"
        if not valid:
            errors += 1
        print(f"  {status:8s} {item.catalog_item_id:40s} {item.display_name}")
    print(f"\n{len(items)} items, {errors} invalid")
    return errors == 0


def list_catalog():
    catalog = MockCatalogAdapter()
    items = catalog.list_items()
    print(f"{'ID':42s} {'Category':15s} {'Status':10s} {'Name'}")
    print("-" * 100)
    for item in items:
        official = " [OFFICIAL]" if item.metadata.get("official_quickstart") else ""
        print(f"{item.catalog_item_id:42s} {item.category.value:15s} {item.status.value:10s} {item.display_name}{official}")
    print(f"\n{len(items)} items total")


def create_tenant(filepath: str):
    import yaml
    with open(filepath) as f:
        data = yaml.safe_load(f)
    tenant = Tenant(**data)
    print(f"Tenant: {tenant.tenant_id}")
    print(f"  Name: {tenant.display_name}")
    print(f"  Type: {tenant.tenant_type.value}")
    print(f"  Status: {tenant.status.value}")
    print(f"  Quota: {tenant.default_quota_profile}")
    print(f"  TTL: {tenant.default_ttl}")
    return tenant


def request_lab(filepath: str):
    import yaml
    with open(filepath) as f:
        data = yaml.safe_load(f)
    svc = ProvisioningService()
    request = LabRequest(**data)
    result = svc.submit_request(request)
    print(f"Request: {result.request_id}")
    print(f"  Status: {result.status.value}")
    print(f"  Tenant: {result.tenant_id}")
    print(f"  Catalog: {result.catalog_item_id}")
    return result


def provision_lab(request_id: str):
    svc = ProvisioningService()
    # Need to first submit a request to get it in the service
    session = svc.provision(request_id)
    print(f"Session: {session.session_id}")
    print(f"  Status: {session.status.value}")
    print(f"  Namespace: {session.namespace}")
    print(f"  Lab URL: {session.lab_url}")
    print(f"  Dashboard: {session.dashboard_url}")
    return session


def validate_lab(session_id: str):
    svc = ProvisioningService()
    session = svc.validate_session(session_id)
    print(f"Session: {session.session_id}")
    print(f"  Status: {session.status.value}")
    for vr in session.validation_results:
        print(f"  {vr.result.value:6s} {vr.check_name}: {vr.message}")
    return session


def handoff(session_id: str):
    svc = ProvisioningService()
    pkg = svc.get_handoff(session_id)
    print(pkg.to_markdown())


def showback(session_id: str):
    svc = ProvisioningService()
    record = svc.get_showback(session_id)
    print(json.dumps(record.model_dump(mode="json"), indent=2))


def repeatability_report(session_id: str):
    svc = ProvisioningService()
    report = svc.get_repeatability_report(session_id)
    print(f"Repeatability Score: {report.repeatability_score}/100")
    print(f"  Catalog Versioned:   {'YES' if report.catalog_versioned else 'NO'}")
    print(f"  Plan Generated:     {'YES' if report.provisioning_plan_generated else 'NO'}")
    print(f"  Validation Passed:  {'YES' if report.validation_passed else 'NO'}")
    print(f"  Handoff Generated:  {'YES' if report.handoff_generated else 'NO'}")
    print(f"  Showback Generated: {'YES' if report.showback_generated else 'NO'}")
    print(f"  Cleanup Defined:    {'YES' if report.cleanup_defined else 'NO'}")


def build_report():
    catalog = MockCatalogAdapter()
    items = catalog.list_items()
    qs = [i for i in items if i.category == CatalogCategory.QUICK_START]
    gb = [i for i in items if i.category == CatalogCategory.GUIDED_BUILD]
    sb = [i for i in items if i.category == CatalogCategory.OPEN_SANDBOX]
    official = [i for i in items if i.metadata.get("official_quickstart")]

    print("Partner AI Launchpad — Build Report")
    print("=" * 50)
    print(f"Total Catalog Items:      {len(items)}")
    print(f"  Quick Starts:           {len(qs)}")
    print(f"  Guided Builds:          {len(gb)}")
    print(f"  Open Sandboxes:         {len(sb)}")
    print(f"  Official AI Quickstarts: {len(official)}")
    print()

    all_valid = validate_catalog()
    print()
    print(f"Catalog Validation: {'PASS' if all_valid else 'FAIL'}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    args = sys.argv[2:]

    commands = {
        "validate-catalog": lambda: validate_catalog(),
        "list-catalog": lambda: list_catalog(),
        "create-tenant": lambda: create_tenant(args[0]) if args else print("Usage: launchpad create-tenant <file>"),
        "request-lab": lambda: request_lab(args[0]) if args else print("Usage: launchpad request-lab <file>"),
        "provision-lab": lambda: provision_lab(args[0]) if args else print("Usage: launchpad provision-lab <request_id>"),
        "validate-lab": lambda: validate_lab(args[0]) if args else print("Usage: launchpad validate-lab <session_id>"),
        "handoff": lambda: handoff(args[0]) if args else print("Usage: launchpad handoff <session_id>"),
        "showback": lambda: showback(args[0]) if args else print("Usage: launchpad showback <session_id>"),
        "repeatability-report": lambda: repeatability_report(args[0]) if args else print("Usage: launchpad repeatability-report <session_id>"),
        "build-report": lambda: build_report(),
    }

    if cmd in commands:
        commands[cmd]()
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
