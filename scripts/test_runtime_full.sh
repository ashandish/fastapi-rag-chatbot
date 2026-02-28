#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

BASE_URL="${BASE_URL:-http://localhost:8000}"
ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-Strongpassword123#}"
AUTO_CHANGE_PASSWORD="${AUTO_CHANGE_PASSWORD:-false}"
NEW_PASSWORD="${NEW_PASSWORD:-}"
POLL_TIMEOUT_SECONDS="${POLL_TIMEOUT_SECONDS:-600}"
POLL_INTERVAL_SECONDS="${POLL_INTERVAL_SECONDS:-3}"

log() {
  echo "[runtime-full] $*"
}

fail() {
  echo "[runtime-full] ERROR: $*" >&2
  exit 1
}

expect_http() {
  local expected="$1"
  local got="$2"
  local what="$3"
  if [[ "$expected" != "$got" ]]; then
    fail "$what expected HTTP $expected, got $got"
  fi
}

extract_location() {
  local headers_file="$1"
  awk 'BEGIN{IGNORECASE=1} /^Location:/{print $2}' "$headers_file" | tr -d '\r' | tail -n1
}

post_login() {
  local user="$1"
  local pass="$2"
  curl -sS \
    -o "$tmp_body" \
    -D "$tmp_headers" \
    -c "$tmp_cookie" \
    -b "$tmp_cookie" \
    -w "%{http_code}" \
    -X POST "$BASE_URL/admin/login" \
    --data-urlencode "username=$user" \
    --data-urlencode "password=$pass"
}

json_get() {
  local key="$1"
  local file="$2"
  python3 - "$key" "$file" <<'PY'
import json, sys
key, path = sys.argv[1], sys.argv[2]
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)
value = data
for part in key.split("."):
    if part.isdigit():
        value = value[int(part)]
    else:
        value = value.get(part)
print("" if value is None else value)
PY
}

tmp_cookie="$(mktemp)"
tmp_headers="$(mktemp)"
tmp_body="$(mktemp)"
tmp_json="$(mktemp)"
tmp_upload="$(mktemp --suffix=.txt)"
trap 'rm -f "$tmp_cookie" "$tmp_headers" "$tmp_body" "$tmp_json" "$tmp_upload"' EXIT

echo "Runtime smoke upload at $(date -u +%FT%TZ)" > "$tmp_upload"

log "Checking public pages..."
code="$(curl -sS -o "$tmp_body" -w "%{http_code}" "$BASE_URL/")"
expect_http "200" "$code" "GET /"
code="$(curl -sS -o "$tmp_body" -w "%{http_code}" "$BASE_URL/chat")"
expect_http "200" "$code" "GET /chat"
code="$(curl -sS -o "$tmp_body" -w "%{http_code}" "$BASE_URL/admin/login")"
expect_http "200" "$code" "GET /admin/login"

log "Logging in as admin..."
code="$(post_login "$ADMIN_USERNAME" "$ADMIN_PASSWORD")"
location="$(extract_location "$tmp_headers")"
if [[ "$code" == "303" && "$location" == "/admin/change-password?notice=default" ]]; then
  if [[ "$AUTO_CHANGE_PASSWORD" != "true" ]]; then
    fail "Default-password flow detected. Re-run with AUTO_CHANGE_PASSWORD=true NEW_PASSWORD='...'"
  fi
  if [[ -z "$NEW_PASSWORD" ]]; then
    fail "AUTO_CHANGE_PASSWORD=true requires NEW_PASSWORD to be set."
  fi

  log "Default password detected, changing admin password..."
  code="$(
    curl -sS \
      -o "$tmp_body" \
      -D "$tmp_headers" \
      -c "$tmp_cookie" \
      -b "$tmp_cookie" \
      -w "%{http_code}" \
      -X POST "$BASE_URL/admin/change-password" \
      --data-urlencode "old_password=$ADMIN_PASSWORD" \
      --data-urlencode "new_password=$NEW_PASSWORD" \
      --data-urlencode "confirm_password=$NEW_PASSWORD"
  )"
  expect_http "200" "$code" "POST /admin/change-password"
  if ! grep -q "Password updated successfully" "$tmp_body"; then
    fail "Password change response did not include success message."
  fi
  ADMIN_PASSWORD="$NEW_PASSWORD"
  code="$(post_login "$ADMIN_USERNAME" "$ADMIN_PASSWORD")"
  location="$(extract_location "$tmp_headers")"
fi

if [[ "$code" != "303" || "$location" != "/embeddings" ]]; then
  if grep -q "Invalid credentials" "$tmp_body"; then
    fail "Admin login failed (invalid credentials)."
  fi
  fail "Admin login expected redirect to /embeddings, got status=$code location='$location'"
fi

log "Validating admin-protected pages..."
code="$(curl -sS -o "$tmp_body" -b "$tmp_cookie" -w "%{http_code}" "$BASE_URL/embeddings")"
expect_http "200" "$code" "GET /embeddings"
code="$(curl -sS -o "$tmp_body" -b "$tmp_cookie" -w "%{http_code}" "$BASE_URL/admin/system-logs")"
expect_http "200" "$code" "GET /admin/system-logs"

log "Validating system logs APIs..."
code="$(curl -sS -o "$tmp_json" -b "$tmp_cookie" -w "%{http_code}" "$BASE_URL/admin/system-logs/api/components")"
expect_http "200" "$code" "GET /admin/system-logs/api/components"
component_count="$(python3 - "$tmp_json" <<'PY'
import json, sys
with open(sys.argv[1], "r", encoding="utf-8") as f:
    data = json.load(f)
print(len(data.get("components", [])))
PY
)"
if [[ "$component_count" -lt 1 ]]; then
  fail "No log components found in /data/system_logs."
fi
component_name="$(json_get "components.0" "$tmp_json")"

code="$(curl -sS -o "$tmp_json" -b "$tmp_cookie" -w "%{http_code}" "$BASE_URL/admin/system-logs/api/files?component=$(python3 - <<PY
import urllib.parse
print(urllib.parse.quote('$component_name', safe=''))
PY
)")"
expect_http "200" "$code" "GET /admin/system-logs/api/files"
file_count="$(python3 - "$tmp_json" <<'PY'
import json, sys
with open(sys.argv[1], "r", encoding="utf-8") as f:
    data = json.load(f)
print(len(data.get("files", [])))
PY
)"
if [[ "$file_count" -lt 1 ]]; then
  fail "No log files found for component '$component_name'."
fi
log_file="$(json_get "files.0" "$tmp_json")"

code="$(curl -sS -o "$tmp_json" -b "$tmp_cookie" -w "%{http_code}" \
  "$BASE_URL/admin/system-logs/api/tail?component=$(python3 - <<PY
import urllib.parse
print(urllib.parse.quote('$component_name', safe=''))
PY
)&log_file=$(python3 - <<PY
import urllib.parse
print(urllib.parse.quote('$log_file', safe=''))
PY
)&lines=100")"
expect_http "200" "$code" "GET /admin/system-logs/api/tail"
if ! python3 - "$tmp_json" <<'PY'
import json, sys
with open(sys.argv[1], "r", encoding="utf-8") as f:
    data = json.load(f)
assert "content" in data and "size_bytes" in data
PY
then
  fail "Tail response did not contain required fields."
fi

log "Submitting embeddings job with a small test file..."
code="$(
  curl -sS \
    -o "$tmp_json" \
    -b "$tmp_cookie" \
    -w "%{http_code}" \
    -X POST "$BASE_URL/embeddings/process" \
    -F "action=add" \
    -F "files=@$tmp_upload;type=text/plain"
)"
expect_http "200" "$code" "POST /embeddings/process"
job_id="$(json_get "job_id" "$tmp_json")"
if [[ -z "$job_id" ]]; then
  fail "Embeddings process response did not include job_id."
fi

log "Polling embeddings progress for job_id=$job_id ..."
start_ts="$(date +%s)"
while true; do
  code="$(curl -sS -o "$tmp_json" -b "$tmp_cookie" -w "%{http_code}" "$BASE_URL/embeddings/progress/$job_id")"
  expect_http "200" "$code" "GET /embeddings/progress/$job_id"
  status="$(json_get "status" "$tmp_json")"
  progress="$(json_get "progress" "$tmp_json")"
  detail="$(json_get "detail" "$tmp_json")"
  log "job status=$status progress=${progress}% detail=$detail"
  if [[ "$status" == "completed" ]]; then
    break
  fi
  if [[ "$status" == "error" ]]; then
    fail "Embeddings job failed. detail=$detail"
  fi
  now="$(date +%s)"
  if (( now - start_ts > POLL_TIMEOUT_SECONDS )); then
    fail "Embeddings job timed out after ${POLL_TIMEOUT_SECONDS}s"
  fi
  sleep "$POLL_INTERVAL_SECONDS"
done

log "PASS: runtime smoke tests completed successfully."
