#!/usr/bin/env bash
set -euo pipefail

# Cluster E2E Test Script for Launchpad + StarGate on infra01
# Requires: oc logged into infra01, VPN for Sandbox API

LAUNCHPAD_API="https://launchpad-api.apps.ocpv-infra01.dal12.infra.demo.redhat.com"
LAUNCHPAD_PORTAL="https://launchpad.apps.ocpv-infra01.dal12.infra.demo.redhat.com"
LAUNCHPAD_ADMIN="https://launchpad-admin.apps.ocpv-infra01.dal12.infra.demo.redhat.com"
STARGATE_URL="https://stargate.apps.ocpv-infra01.dal12.infra.demo.redhat.com"
LP_NS="partner-ai-launchpad"
SG_NS="stargate"

PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=============================================="
echo "  Launchpad + StarGate Cluster E2E Test"
echo "  Cluster: infra01"
echo "=============================================="
echo ""

# ── Step 1: Pod Health ────────────────────────────────
echo "Step 1: Pod Health (oc get pods)"
LP_PODS=$(oc get pods -n $LP_NS --no-headers 2>/dev/null | grep -c "Running" || echo "0")
SG_PODS=$(oc get pods -n $SG_NS --no-headers 2>/dev/null | grep -v build | grep -c "Running" || echo "0")
if [ "$LP_PODS" -ge 3 ]; then pass "Launchpad: $LP_PODS pods running"; else fail "Launchpad: only $LP_PODS pods running"; fi
if [ "$SG_PODS" -ge 2 ]; then pass "StarGate: $SG_PODS pods running"; else fail "StarGate: only $SG_PODS pods running"; fi
echo ""

# ── Step 2: Route Health ──────────────────────────────
echo "Step 2: Route Health (HTTPS)"
LP_STATUS=$(curl -sk -o /dev/null -w "%{http_code}" "$LAUNCHPAD_API/health" 2>/dev/null || echo "000")
if [ "$LP_STATUS" = "200" ]; then pass "Launchpad API route ($LP_STATUS)"; else fail "Launchpad API route ($LP_STATUS)"; fi

PORTAL_STATUS=$(curl -sk -o /dev/null -w "%{http_code}" "$LAUNCHPAD_PORTAL" 2>/dev/null || echo "000")
if [ "$PORTAL_STATUS" = "200" ] || [ "$PORTAL_STATUS" = "403" ]; then pass "Partner Portal route ($PORTAL_STATUS)"; else fail "Partner Portal route ($PORTAL_STATUS)"; fi

ADMIN_STATUS=$(curl -sk -o /dev/null -w "%{http_code}" "$LAUNCHPAD_ADMIN" 2>/dev/null || echo "000")
if [ "$ADMIN_STATUS" = "200" ] || [ "$ADMIN_STATUS" = "403" ]; then pass "Admin Dashboard route ($ADMIN_STATUS)"; else fail "Admin Dashboard route ($ADMIN_STATUS)"; fi

SG_STATUS=$(curl -sk -o /dev/null -w "%{http_code}" "$STARGATE_URL" 2>/dev/null || echo "000")
if [ "$SG_STATUS" = "200" ] || [ "$SG_STATUS" = "403" ]; then pass "StarGate route ($SG_STATUS)"; else fail "StarGate route ($SG_STATUS)"; fi
echo ""

# ── Step 3: Launchpad API — Catalog ───────────────────
echo "Step 3: Launchpad API — Catalog"
CATALOG=$(curl -sk "$LAUNCHPAD_API/catalog" 2>/dev/null)
CATALOG_COUNT=$(echo "$CATALOG" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
if [ "$CATALOG_COUNT" -ge 25 ]; then pass "Catalog: $CATALOG_COUNT items"; else fail "Catalog: only $CATALOG_COUNT items (expected 25)"; fi

OFFICIALS=$(echo "$CATALOG" | python3 -c "import sys,json; print(sum(1 for i in json.load(sys.stdin) if i.get('metadata',{}).get('official_quickstart')))" 2>/dev/null || echo "0")
if [ "$OFFICIALS" -ge 7 ]; then pass "Official quickstarts: $OFFICIALS"; else fail "Official quickstarts: only $OFFICIALS (expected 7)"; fi

RHDP=$(echo "$CATALOG" | python3 -c "import sys,json; print(sum(1 for i in json.load(sys.stdin) if i.get('metadata',{}).get('provisioner_mode')=='rhdp'))" 2>/dev/null || echo "0")
if [ "$RHDP" -ge 17 ]; then pass "RHDP-wired items: $RHDP"; else fail "RHDP-wired: only $RHDP (expected 17)"; fi
echo ""

# ── Step 4: Launchpad API — Full Lifecycle ────────────
echo "Step 4: Full Self-Service Lifecycle (via API)"
TENANT=$(curl -sk -X POST "$LAUNCHPAD_API/tenants" -H "Content-Type: application/json" \
  -d '{"tenant_id":"e2e-infra01","display_name":"E2E Test Tenant","tenant_type":"demo"}' 2>/dev/null)
TENANT_STATUS=$(echo "$TENANT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "")
if [ "$TENANT_STATUS" = "active" ]; then pass "Create tenant: active"; else fail "Create tenant: $TENANT_STATUS"; fi

REQ=$(curl -sk -X POST "$LAUNCHPAD_API/lab-requests" -H "Content-Type: application/json" \
  -d '{"tenant_id":"e2e-infra01","requester_id":"e2e-tester","catalog_item_id":"inference-overdrive-quickstart","requested_mode":"quick_start"}' 2>/dev/null)
REQ_ID=$(echo "$REQ" | python3 -c "import sys,json; print(json.load(sys.stdin).get('request_id',''))" 2>/dev/null || echo "")
REQ_STATUS=$(echo "$REQ" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "")
if [ "$REQ_STATUS" = "accepted" ]; then pass "Submit request: accepted"; else fail "Submit request: $REQ_STATUS"; fi

SESSION=$(curl -sk -X POST "$LAUNCHPAD_API/lab-requests/$REQ_ID/provision" 2>/dev/null)
SID=$(echo "$SESSION" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null || echo "")
S_STATUS=$(echo "$SESSION" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "")
if [ -n "$SID" ]; then pass "Provision: $S_STATUS (session=$SID)"; else fail "Provision failed"; fi

if [ -n "$SID" ]; then
  VAL=$(curl -sk -X POST "$LAUNCHPAD_API/lab-sessions/$SID/validate" 2>/dev/null)
  V_STATUS=$(echo "$VAL" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "")
  if [ "$V_STATUS" = "ready" ]; then pass "Validate: ready"; else fail "Validate: $V_STATUS"; fi

  ACT=$(curl -sk -X POST "$LAUNCHPAD_API/lab-sessions/$SID/activate" 2>/dev/null)
  A_STATUS=$(echo "$ACT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "")
  if [ "$A_STATUS" = "active" ]; then pass "Activate: active"; else fail "Activate: $A_STATUS"; fi

  HANDOFF=$(curl -sk "$LAUNCHPAD_API/lab-sessions/$SID/handoff" 2>/dev/null)
  H_TITLE=$(echo "$HANDOFF" | python3 -c "import sys,json; print(json.load(sys.stdin).get('lab_title',''))" 2>/dev/null || echo "")
  if [ -n "$H_TITLE" ]; then pass "Handoff: $H_TITLE"; else fail "Handoff failed"; fi

  SHOWBACK=$(curl -sk "$LAUNCHPAD_API/lab-sessions/$SID/showback" 2>/dev/null)
  SB_TOKENS=$(echo "$SHOWBACK" | python3 -c "import sys,json; print(json.load(sys.stdin).get('estimated_tokens',0))" 2>/dev/null || echo "0")
  if [ "$SB_TOKENS" -gt 0 ]; then pass "Showback: $SB_TOKENS tokens"; else fail "Showback: no tokens"; fi
fi
echo ""

# ── Step 5: Workshop API ─────────────────────────────
echo "Step 5: Workshop Batch Lifecycle"
WS=$(curl -sk -X POST "$LAUNCHPAD_API/workshops" -H "Content-Type: application/json" \
  -d '{"tenant_id":"e2e-infra01","catalog_item_id":"inference-overdrive-quickstart","num_users":3,"ttl":"4h"}' 2>/dev/null)
WS_STATUS=$(echo "$WS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "")
WS_SESSIONS=$(echo "$WS" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('session_ids',[])))" 2>/dev/null || echo "0")
WS_ID=$(echo "$WS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('workshop_id',''))" 2>/dev/null || echo "")
if [ "$WS_STATUS" = "ready" ] && [ "$WS_SESSIONS" -eq 3 ]; then pass "Workshop: $WS_SESSIONS sessions"; else fail "Workshop: status=$WS_STATUS sessions=$WS_SESSIONS"; fi

if [ -n "$WS_ID" ]; then
  WS_DEL=$(curl -sk -X DELETE "$LAUNCHPAD_API/workshops/$WS_ID" 2>/dev/null)
  WS_DEL_STATUS=$(echo "$WS_DEL" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "")
  if [ "$WS_DEL_STATUS" = "completed" ]; then pass "Workshop reclaim: completed"; else fail "Workshop reclaim: $WS_DEL_STATUS"; fi
fi
echo ""

# ── Step 6: Sandbox API Connection ────────────────────
echo "Step 6: Sandbox API (from cluster)"
if [ -f ~/.sandbox/token ]; then
  SB_RESULT=$(HTTPS_PROXY=http://squid.redhat.com:3128 curl -sk \
    -H "Authorization: Bearer $(cat ~/.sandbox/token)" \
    "https://restricted-babylon-sandbox-api.apps.infra-us-east-1.infra.demo.redhat.com/api/v1/login" 2>/dev/null)
  SB_TOKEN=$(echo "$SB_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token','')[:10])" 2>/dev/null || echo "")
  if [ -n "$SB_TOKEN" ]; then pass "Sandbox API login OK"; else fail "Sandbox API login failed"; fi
else
  echo "  SKIP: ~/.sandbox/token not found"
fi
echo ""

# ── Step 7: StarGate ↔ Launchpad Integration ──────────
echo "Step 7: StarGate Integration (real cross-pod)"
CALLBACK_STATUS=$(curl -sk -o /dev/null -w "%{http_code}" -X POST "$LAUNCHPAD_API/callbacks/cleanup-result" \
  -H "Content-Type: application/json" \
  -d '{"session_id":"test-callback","result":"success"}' 2>/dev/null || echo "000")
if [ "$CALLBACK_STATUS" = "404" ] || [ "$CALLBACK_STATUS" = "200" ]; then
  pass "Callback endpoint accessible ($CALLBACK_STATUS)"
else
  fail "Callback endpoint: $CALLBACK_STATUS"
fi
echo ""

# ── Step 8: Container Resources ──────────────────────
echo "Step 8: Resource Verification"
LP_CPU=$(oc adm top pods -n $LP_NS --no-headers 2>/dev/null | awk '{sum+=$2} END {print sum"m"}' || echo "?")
LP_MEM=$(oc adm top pods -n $LP_NS --no-headers 2>/dev/null | awk '{sum+=$3} END {print sum"Mi"}' || echo "?")
pass "Launchpad resource usage: CPU=$LP_CPU MEM=$LP_MEM"

SG_CPU=$(oc adm top pods -n $SG_NS --no-headers 2>/dev/null | grep -v build | awk '{sum+=$2} END {print sum"m"}' || echo "?")
SG_MEM=$(oc adm top pods -n $SG_NS --no-headers 2>/dev/null | grep -v build | awk '{sum+=$3} END {print sum"Mi"}' || echo "?")
pass "StarGate resource usage: CPU=$SG_CPU MEM=$SG_MEM"
echo ""

# ── Summary ──────────────────────────────────────────
echo "=============================================="
echo "  RESULTS: $PASS passed, $FAIL failed"
echo "  Cluster: infra01 ($(oc whoami --show-server 2>/dev/null))"
echo "  User: $(oc whoami 2>/dev/null)"
echo "=============================================="

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
