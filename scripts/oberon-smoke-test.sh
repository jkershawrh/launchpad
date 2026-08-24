#!/usr/bin/env bash
set -euo pipefail

# Oberon Smoke Test — validates the full Launchpad API lifecycle
#
# Usage:
#   export LAUNCHPAD_API=https://launchpad-api.apps.oberon.fm2aihpcsed.com
#   export API_KEY=your-api-key
#   ./scripts/oberon-smoke-test.sh

LAUNCHPAD_API="${LAUNCHPAD_API:-https://launchpad-api.apps.oberon.fm2aihpcsed.com}"
API_KEY="${API_KEY:?Set API_KEY environment variable}"
CURL="curl -sf -H X-API-Key:${API_KEY} -H Content-Type:application/json"

echo "=== Oberon Smoke Test ==="
echo "API: ${LAUNCHPAD_API}"
echo ""

# 1. Health check
echo "1. Health check..."
$CURL "${LAUNCHPAD_API}/health" | python3 -m json.tool
echo ""

echo "   Detailed health..."
$CURL "${LAUNCHPAD_API}/health/detailed" | python3 -m json.tool
echo ""

# 2. List catalog
echo "2. Catalog..."
CATALOG=$($CURL "${LAUNCHPAD_API}/api/v1/catalog")
COUNT=$(echo "$CATALOG" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")
echo "   ${COUNT} items in catalog"

SMOKE=$(echo "$CATALOG" | python3 -c "
import sys, json
items = json.load(sys.stdin)
smoke = [i for i in items if i['catalog_item_id'] == 'smoke-test']
print('FOUND' if smoke else 'MISSING')
")
echo "   smoke-test demo: ${SMOKE}"
if [ "$SMOKE" = "MISSING" ]; then
    echo "   ERROR: smoke-test demo not found in catalog"
    exit 1
fi
echo ""

# 3. Create tenant
echo "3. Creating tenant..."
TENANT=$($CURL -X POST "${LAUNCHPAD_API}/api/v1/tenants" -d '{
    "tenant_id": "smoke-test-tenant",
    "display_name": "Smoke Test Tenant",
    "tenant_type": "demo"
}' 2>/dev/null || echo '{"tenant_id":"smoke-test-tenant"}')
echo "   Tenant: smoke-test-tenant"
echo ""

# 4. Submit request
echo "4. Submitting lab request..."
REQUEST=$($CURL -X POST "${LAUNCHPAD_API}/api/v1/lab-requests" -d '{
    "tenant_id": "smoke-test-tenant",
    "requester_id": "smoke-tester",
    "catalog_item_id": "smoke-test",
    "requested_mode": "quick_start"
}')
REQUEST_ID=$(echo "$REQUEST" | python3 -c "import sys,json; print(json.load(sys.stdin)['request_id'])")
STATUS=$(echo "$REQUEST" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
echo "   Request: ${REQUEST_ID}"
echo "   Status: ${STATUS}"
if [ "$STATUS" != "accepted" ]; then
    echo "   ERROR: request not accepted (status: ${STATUS})"
    exit 1
fi
echo ""

echo "=== Smoke Test PASSED ==="
echo ""
echo "Next steps (manual):"
echo "  - Provision: POST /api/v1/lab-requests/${REQUEST_ID}/provision"
echo "  - This requires OpenShift cluster access from the backend pod"
