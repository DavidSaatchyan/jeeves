#!/usr/bin/env bash
# Smoke-test the Jeeves API. Run after starting the server locally.
set -euo pipefail
BASE=${BASE:-http://localhost:8000}
EMAIL="demo_$(date +%s)@example.com"
PASS="password123"

echo "== Register =="
REG=$(curl -sS -X POST "$BASE/auth/register" -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\",\"tenant_name\":\"Demo\"}")
echo "$REG"
TOKEN=$(echo "$REG" | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
TID=$(echo   "$REG" | python -c "import sys,json;print(json.load(sys.stdin)['tenant_id'])")
echo "tenant=$TID"

echo "== Health =="
curl -sS "$BASE/health"; echo

echo "== Upload KB =="
mkdir -p /tmp/jv && cat > /tmp/jv/kb.txt <<'EOF'
Jeeves subscription plans:
- Free: 100 dialogs, 14-day trial.
- Business: $49/month, unlimited dialogs.
- Enterprise: contact sales.
EOF
curl -sS -X POST "$BASE/knowledge/files" -H "Authorization: Bearer $TOKEN" -F "file=@/tmp/jv/kb.txt"; echo

echo "== List files =="
curl -sS "$BASE/knowledge/files" -H "Authorization: Bearer $TOKEN"; echo

echo "== Chat (allow time for indexing) =="
sleep 8
curl -sS -X POST "$BASE/chat" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"user_id":"demo_user","message":"What subscription plans do you offer?"}'; echo

echo "== Widget chat =="
curl -sS -X POST "$BASE/widget/chat" -H "Content-Type: application/json" \
  -d "{\"tenant_id\":\"$TID\",\"user_id\":\"demo_user\",\"message\":\"hi\"}"; echo

echo "Done."
