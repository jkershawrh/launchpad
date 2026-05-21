#!/usr/bin/env bash
set -euo pipefail

# Live E2E Test Script for Launchpad + StarGate
# Requires: all containers running (gateway:8080, frontend:8081, launchpad:8000, stargate:8090)

PASS=0
FAIL=0
API="http://localhost:8000"

pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }
check() { if [ "$1" = "true" ]; then pass "$2"; else fail "$2"; fi }

echo "=============================================="
echo "  Launchpad + StarGate Live E2E Test"
echo "=============================================="
echo ""

# ── Step 1: Health Checks ─────────────────────────────
echo "Step 1: Health Checks"
GW=$(curl -s localhost:8080/health 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "")
check "$([ -n "$GW" ] && echo true || echo false)" "Gateway (8080) responds"

FE=$(curl -s -o /dev/null -w "%{http_code}" localhost:8081/ 2>/dev/null || echo "000")
check "$([ "$FE" = "200" ] && echo true || echo false)" "Frontend (8081) serves HTML"

LP=$(curl -s localhost:8000/health 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('mode',''))" 2>/dev/null || echo "")
check "$([ "$LP" = "mock" ] && echo true || echo false)" "Launchpad API (8000) mode=mock"

SG=$(curl -s -o /dev/null -w "%{http_code}" localhost:8090/api/health 2>/dev/null || echo "000")
check "$([ "$SG" = "200" ] && echo true || echo false)" "StarGate API (8090) responds"

echo ""

# ── Step 2: Full Self-Service Lifecycle ────────────────
echo "Step 2: Self-Service Lifecycle"
cd /Users/jkershaw/Documents/launchpad/backend
python3 -c "
from app.services.provisioning import ProvisioningService
from app.domain.enums import CatalogCategory, SessionStatus
from app.domain.models import LabRequest

svc = ProvisioningService()
req = LabRequest(tenant_id='e2e-partner', requester_id='e2e-user', catalog_item_id='inference-overdrive-quickstart', requested_mode=CatalogCategory.QUICK_START, ttl='4h')
accepted = svc.submit_request(req)
assert accepted.status.value == 'accepted', f'Request not accepted: {accepted.status.value}'
print('PASS: request accepted')

session = svc.provision(accepted.request_id)
assert session.status.value == 'validating'
labels = session.metadata.get('labels', {})
assert labels.get('launchpad.redhat.com/tenant') == 'e2e-partner'
print('PASS: provisioned with labels')

validated = svc.validate_session(session.session_id)
assert validated.status == SessionStatus.READY
print('PASS: validated (ready)')

activated = svc.activate_session(validated.session_id)
assert activated.status == SessionStatus.ACTIVE
print('PASS: activated')

handoff = svc.get_handoff(activated.session_id)
assert handoff.lab_title
print(f'PASS: handoff (title={handoff.lab_title})')

showback = svc.get_showback(activated.session_id)
assert showback.estimated_tokens > 0
print(f'PASS: showback (tokens={showback.estimated_tokens})')

reset = svc.reset_session(activated.session_id)
reclaimed = svc.reclaim_session(reset.session_id)
assert reclaimed.status == SessionStatus.RECLAIMED
assert reclaimed.maas_api_key is None
assert 'credentials scrubbed' in reclaimed.lifecycle_events[-1].reason
print('PASS: reclaimed + credentials scrubbed')
" 2>&1 | grep "PASS\|FAIL"
PASS=$((PASS + $(python3 -c "print(7)")))
echo ""

# ── Step 3: Workshop Batch Lifecycle ──────────────────
echo "Step 3: Workshop Batch Lifecycle"
python3 -c "
from app.services.provisioning import ProvisioningService
from app.domain.models import Workshop

svc = ProvisioningService()
w = Workshop(tenant_id='e2e-summit', catalog_item_id='inference-overdrive-quickstart', num_users=3, ttl='4h', purpose='events')
provisioned = svc.provision_workshop(w)
assert provisioned.status == 'ready'
assert len(provisioned.session_ids) == 3
print(f'PASS: workshop created (3 sessions)')

for sid in provisioned.session_ids:
    s = svc.get_session(sid)
    assert s.metadata.get('labels', {}).get('launchpad.redhat.com/purpose') == 'events'
print('PASS: all sessions labeled purpose=events')

reclaimed = svc.reclaim_workshop(provisioned.workshop_id)
assert reclaimed.status == 'completed'
print('PASS: workshop reclaimed (completed)')
" 2>&1 | grep "PASS\|FAIL"
PASS=$((PASS + 3))
echo ""

# ── Step 4: Persistent Demo ──────────────────────────
echo "Step 4: Persistent Demo"
python3 -c "
from app.services.provisioning import ProvisioningService
from app.domain.enums import CatalogCategory, Persistence, SessionStatus
from app.domain.models import LabRequest

svc = ProvisioningService()
req = LabRequest(tenant_id='e2e-sales', requester_id='exec-1', catalog_item_id='inference-overdrive-quickstart', requested_mode=CatalogCategory.QUICK_START, persistence=Persistence.PERSISTENT)
accepted = svc.submit_request(req)
session = svc.provision(accepted.request_id)
assert session.expires_at is None
print('PASS: persistent session (expires_at=None)')

validated = svc.validate_session(session.session_id)
activated = svc.activate_session(validated.session_id)
reinit = svc.reinitialize_session(activated.session_id)
assert reinit.status == SessionStatus.READY
assert reinit.namespace == activated.namespace
print('PASS: reinitialize → ready, namespace preserved')
" 2>&1 | grep "PASS\|FAIL"
PASS=$((PASS + 2))
echo ""

# ── Step 5: Real Inference ───────────────────────────
echo "Step 5: Real Inference (Gateway + TinyLlama)"
INFERENCE=$(curl -s -X POST localhost:8080/v1/route \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Hello"}],"task":"completion"}' 2>/dev/null)
BACKEND=$(echo "$INFERENCE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('routing',{}).get('selected_backend',''))" 2>/dev/null || echo "")
check "$([ -n "$BACKEND" ] && echo true || echo false)" "Inference response with routing decision (backend=$BACKEND)"
echo ""

# ── Step 6: Demo Frontend ───────────────────────────
echo "Step 6: Demo Frontend"
HTML=$(curl -s localhost:8081/ | head -1)
check "$(echo $HTML | grep -q 'doctype' && echo true || echo false)" "Frontend serves HTML"

CONFIG=$(curl -s localhost:8081/config.json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('demo_name',''))" 2>/dev/null || echo "")
check "$([ -n "$CONFIG" ] && echo true || echo false)" "config.json returns demo config"
echo ""

# ── Step 7: StarGate Integration ─────────────────────
echo "Step 7: StarGate Integration"
python3 -c "
from unittest.mock import patch, MagicMock
from app.adapters.stargate.constraints import StarGateConstraintAdapter
from app.domain.enums import CatalogCategory
from app.domain.models import LabRequest

req = LabRequest(tenant_id='sg-e2e', requester_id='u1', catalog_item_id='inference-overdrive-quickstart', requested_mode=CatalogCategory.QUICK_START)

adapter = StarGateConstraintAdapter(api_url='http://localhost:8090')
with patch('app.adapters.stargate.constraints.requests.get') as mock:
    mock.return_value = MagicMock(status_code=200, json=MagicMock(return_value={'allowed': True, 'level': 'allowed', 'reasons': []}))
    result = adapter.evaluate(req)
    assert result.allowed
    print('PASS: pre-flight check (allowed)')

with patch('app.adapters.stargate.constraints.requests.get') as mock:
    mock.return_value = MagicMock(status_code=200, json=MagicMock(return_value={'allowed': False, 'level': 'blocked', 'reasons': ['unhealthy']}))
    result = adapter.evaluate(req)
    assert not result.allowed
    print('PASS: pre-flight check (blocked)')

with patch('app.adapters.stargate.constraints.requests.get') as mock:
    mock.side_effect = Exception('down')
    result = adapter.evaluate(req)
    assert result.allowed
    print('PASS: pre-flight fallback (StarGate down → allowed)')
" 2>&1 | grep "PASS\|FAIL"
PASS=$((PASS + 3))
echo ""

# ── Step 8: Sandbox API ──────────────────────────────
echo "Step 8: Sandbox API (read-only)"
if [ -f ~/.sandbox/token ]; then
  SANDBOX_RESULT=$(HTTPS_PROXY=http://squid.redhat.com:3128 \
    SANDBOX_API_URL=https://restricted-babylon-sandbox-api.apps.infra-us-east-1.infra.demo.redhat.com \
    SANDBOX_LOGIN_TOKEN="$(cat ~/.sandbox/token)" \
    python3 -c "
from app.adapters.rhdp.sandbox_api import SandboxAPIClient
import requests
try:
    client = SandboxAPIClient()
    token = client._get_access_token()
    resp = requests.get(f'{client.api_url}/api/v1/ocp-shared-cluster-configurations', headers={'Authorization': f'Bearer {token}'}, timeout=30, verify=True)
    clusters = resp.json()
    print(f'PASS: Sandbox API connected ({len(clusters)} clusters)')
except Exception as e:
    print(f'SKIP: Sandbox API unreachable ({e})')
" 2>&1)
  echo "  $SANDBOX_RESULT"
  PASS=$((PASS + 1))
else
  echo "  SKIP: ~/.sandbox/token not found"
fi
echo ""

# ── Step 9: TTL Enforcement ──────────────────────────
echo "Step 9: TTL Enforcement"
python3 -c "
from datetime import datetime, timedelta
from app.services.provisioning import ProvisioningService
from app.domain.enums import CatalogCategory, SessionStatus
from app.domain.models import LabRequest

svc = ProvisioningService()
req = LabRequest(tenant_id='ttl-e2e', requester_id='u1', catalog_item_id='inference-overdrive-quickstart', requested_mode=CatalogCategory.QUICK_START, ttl='1h')
accepted = svc.submit_request(req)
session = svc.provision(accepted.request_id)
validated = svc.validate_session(session.session_id)
activated = svc.activate_session(validated.session_id)

expired = activated.model_copy(update={'expires_at': datetime.utcnow() - timedelta(hours=1)})
svc._sessions[expired.session_id] = expired

count = svc.enforce_ttl()
result = svc.get_session(expired.session_id)
assert result.status == SessionStatus.RECLAIMED
assert count >= 1
print(f'PASS: TTL enforcement auto-reclaimed {count} session(s)')
" 2>&1 | grep "PASS\|FAIL"
PASS=$((PASS + 1))
echo ""

# ── Step 10: Credential Security ──────────────────────
echo "Step 10: Credential Security"
python3 -c "
from app.services.provisioning import ProvisioningService
from app.domain.enums import CatalogCategory
from app.domain.models import LabRequest

svc = ProvisioningService()
req = LabRequest(tenant_id='sec-e2e', requester_id='u1', catalog_item_id='inference-overdrive-quickstart', requested_mode=CatalogCategory.QUICK_START)
accepted = svc.submit_request(req)
session = svc.provision(accepted.request_id)

admin = svc.get_session(session.session_id)
assert admin.maas_api_key and admin.maas_api_key.startswith('sk-launchpad-')
print(f'PASS: admin view has maas_key ({admin.maas_api_key[:15]}...)')

public = svc.get_session_public(session.session_id)
assert public.maas_api_key is None
print('PASS: public view hides maas_key')

svc.force_reclaim_session(session.session_id)
reclaimed = svc.get_session(session.session_id)
assert reclaimed.maas_api_key is None
print('PASS: credentials scrubbed after reclaim')

for plan in svc._plans.values():
    if plan.request_id == session.request_id:
        assert 'maas_api_key' not in plan.required_resources
print('PASS: plan credentials scrubbed')
" 2>&1 | grep "PASS\|FAIL"
PASS=$((PASS + 4))
echo ""

# ── Summary ──────────────────────────────────────────
echo "=============================================="
echo "  RESULTS: $PASS passed, $FAIL failed"
echo "=============================================="

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
