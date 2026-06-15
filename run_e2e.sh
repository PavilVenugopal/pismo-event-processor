#!/usr/bin/env bash
# End-to-end test runner for pismo-event-processor.
# Runs unit tests, spins up the full Docker stack, runs integration tests,
# prints a summary of what landed in DynamoDB and the DLQ, then tears down.

set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "${GREEN}✓ $*${NC}"; }
fail() { echo -e "${RED}✗ $*${NC}"; exit 1; }
info() { echo -e "${YELLOW}→ $*${NC}"; }

# ── prereqs ──────────────────────────────────────────────────────────────────

info "Checking prerequisites..."

command -v docker   >/dev/null 2>&1 || fail "docker not found"
command -v python3  >/dev/null 2>&1 || fail "python3 not found"

if docker compose version >/dev/null 2>&1; then
    COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE="docker-compose"
else
    fail "docker compose not found (install Docker Desktop or the compose plugin)"
fi

pass "Prerequisites OK  (compose: $COMPOSE)"

# ── unit tests ────────────────────────────────────────────────────────────────

info "Installing dev dependencies..."
pip3 install -q -r requirements-dev.txt

info "Running unit tests..."
if python3 -m pytest tests/ --ignore=tests/test_e2e.py --ignore=tests/test_store.py -q; then
    pass "Unit tests passed"
else
    fail "Unit tests failed — fix these before running e2e"
fi

# ── docker stack ──────────────────────────────────────────────────────────────

cleanup() {
    info "Tearing down Docker stack..."
    $COMPOSE down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

info "Starting Docker stack..."
$COMPOSE down -v --remove-orphans >/dev/null 2>&1 || true
$COMPOSE up --build -d

info "Waiting for LocalStack to be healthy..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:4566/_localstack/health >/dev/null 2>&1; then
        pass "LocalStack is up"
        break
    fi
    if [ "$i" -eq 30 ]; then
        fail "LocalStack did not become healthy in time"
    fi
    sleep 2
done

info "Waiting for infra-init to complete..."
for i in $(seq 1 20); do
    status=$($COMPOSE ps infra-init --format json 2>/dev/null | python3 -c "
import sys, json
data = sys.stdin.read().strip()
if not data:
    print('pending')
else:
    rows = json.loads(data) if data.startswith('[') else [json.loads(data)]
    print(rows[0].get('State', 'pending'))
" 2>/dev/null || echo "pending")

    if [ "$status" = "exited" ] || [ "$status" = "Exit 0" ]; then
        pass "Infra init complete"
        break
    fi
    if [ "$i" -eq 20 ]; then
        echo ""
        $COMPOSE logs infra-init
        fail "infra-init did not complete — see logs above"
    fi
    sleep 2
done

# Give the processor a moment to start polling
sleep 3

# ── e2e tests ─────────────────────────────────────────────────────────────────

info "Running end-to-end tests..."
if RUN_INTEGRATION=1 python3 -m pytest tests/test_e2e.py -v -s; then
    pass "E2E tests passed"
else
    echo ""
    info "Processor logs:"
    $COMPOSE logs --tail=40 processor
    fail "E2E tests failed — see processor logs above"
fi

# ── results summary ───────────────────────────────────────────────────────────

echo ""
info "DynamoDB — events table:"
python3 - <<'EOF'
import boto3, json
from decimal import Decimal

def default(o):
    return float(o) if isinstance(o, Decimal) else str(o)

ddb = boto3.resource("dynamodb",
    region_name="us-east-1",
    endpoint_url="http://localhost:4566",
    aws_access_key_id="test",
    aws_secret_access_key="test",
)
table = ddb.Table("events")
resp = table.scan()
items = resp.get("Items", [])
print(f"  {len(items)} item(s) found")
for item in items[:5]:
    print(f"  · {item.get('event_type')} | tenant={item.get('tenant_id')} | event_id={item.get('event_id')}")
if len(items) > 5:
    print(f"  ... and {len(items) - 5} more")
EOF

echo ""
info "DLQ — events-dlq:"
python3 - <<'EOF'
import boto3, json

sqs = boto3.client("sqs",
    region_name="us-east-1",
    endpoint_url="http://localhost:4566",
    aws_access_key_id="test",
    aws_secret_access_key="test",
)
url = "http://localhost:4566/000000000000/events-dlq"
resp = sqs.receive_message(QueueUrl=url, MaxNumberOfMessages=10, WaitTimeSeconds=3)
msgs = resp.get("Messages", [])
print(f"  {len(msgs)} message(s) in DLQ")
for msg in msgs:
    body = json.loads(msg["Body"])
    evt = body.get("event", {})
    print(f"  · {evt.get('event_type')} | reason={body.get('reason')} | event_id={evt.get('event_id')}")
EOF

echo ""
pass "All done."
