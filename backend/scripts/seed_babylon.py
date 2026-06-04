#!/usr/bin/env python3
"""One-time seed script — pull historical provisioning data from Babylon."""
import json
import os
import sys

sys.path.insert(0, "/opt/app-root/src")
os.environ.setdefault("BABYLON_KUBECONFIG", "/opt/babylon-secrets/kubeconfig")

from app.services.data_seeder import DataSeeder

seeder = DataSeeder()
result = seeder.seed_from_babylon()

if "error" in result:
    print(f"Error: {result['error']}")
    sys.exit(1)

print(f"Total subjects: {result['total_subjects']}")
print(f"Prod: {result['prod']}, Event: {result['event']}, Dev: {result['dev']}")
print(f"Success: {result['success']}, Failed: {result['failed']}")
print(f"Catalog items: {result['catalog_items']}")

outcomes = result.get("outcomes", [])
event_items = sorted(set(o["catalog_item"] for o in outcomes if o.get("stage") == "event"))
print(f"\nEvent (Summit) catalog items ({len(event_items)}):")
for item in event_items:
    print(f"  {item}")

prod_items = sorted(set(o["catalog_item"] for o in outcomes if o.get("stage") == "prod"))
print(f"\nProduction catalog items ({len(prod_items)}):")
for item in prod_items[:20]:
    print(f"  {item}")
if len(prod_items) > 20:
    print(f"  ... ({len(prod_items)} total)")

print(f"\nDone. {len(outcomes)} outcomes ready for FeedbackTracker.")
