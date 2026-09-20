from __future__ import annotations

import json
import os
from pathlib import Path

from app.domain.catalog_intake_discovery import (
    CatalogIntakeDiscoveryRequest,
    CatalogIntakeSourceApproval,
)
from app.services.catalog_intake_discovery import CatalogIntakeDiscoveryRunner


def main() -> int:
    try:
        request = CatalogIntakeDiscoveryRequest.model_validate_json(
            os.environ["CATALOG_INTAKE_REQUEST_JSON"]
        )
        approval = CatalogIntakeSourceApproval.model_validate_json(
            os.environ["CATALOG_INTAKE_SOURCE_APPROVAL_JSON"]
        )
        workspace = Path(os.environ.get("CATALOG_INTAKE_WORKSPACE", "/workspace"))
        receipt = CatalogIntakeDiscoveryRunner(
            source_approvals=[approval],
            workspace_parent=workspace,
        ).run(request)
        print(receipt.model_dump_json())
        return 0 if receipt.status == "passed" else 2
    except Exception:  # noqa: BLE001 - bootstrap output must never leak request data
        # Never print request data, source content, environment values, or exception text.
        print(json.dumps({"status": "failed", "error_codes": ["worker-bootstrap-failed"]}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
