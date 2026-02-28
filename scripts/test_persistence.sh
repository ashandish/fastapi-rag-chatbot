#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

BASE_URL="${BASE_URL:-http://localhost:8000}"
ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
BOOTSTRAP_PASSWORD="${BOOTSTRAP_PASSWORD:-Strongpassword123#}"
NEW_PASSWORD="${NEW_PASSWORD:-PersistPass123#}"
STARTUP_TIMEOUT_SECONDS="${STARTUP_TIMEOUT_SECONDS:-240}"

log() {
  echo "[persistence] $*"
}

fail() {
  echo "[persistence] ERROR: $*" >&2
  exit 1
}

wait_for_app() {
  local start_ts now elapsed
  start_ts="$(date +%s)"
  while true; do
    if curl -fsS "$BASE_URL/admin/login" >/dev/null 2>&1; then
      return 0
    fi
    now="$(date +%s)"
    elapsed=$((now - start_ts))
    if (( elapsed >= STARTUP_TIMEOUT_SECONDS )); then
      return 1
    fi
    sleep 2
  done
}

extract_location() {
  local headers_file="$1"
  awk 'BEGIN{IGNORECASE=1} /^Location:/{print $2}' "$headers_file" | tr -d '\r' | tail -n1
}

post_login() {
  local user="$1"
  local pass="$2"
  local cookie_file="$3"
  local headers_file="$4"
  local body_file="$5"

  curl -sS \
    -o "$body_file" \
    -D "$headers_file" \
    -c "$cookie_file" \
    -b "$cookie_file" \
    -w "%{http_code}" \
    -X POST "$BASE_URL/admin/login" \
    --data-urlencode "username=$user" \
    --data-urlencode "password=$pass"
}

tmp_cookie="$(mktemp)"
tmp_headers="$(mktemp)"
tmp_body="$(mktemp)"
trap 'rm -f "$tmp_cookie" "$tmp_headers" "$tmp_body"' EXIT

log "Preparing deterministic baseline..."
docker compose down -v --remove-orphans
docker compose up -d --build redis ollama

log "Initializing Ollama model via ollama-init..."
docker compose run --rm ollama-init

log "Starting app services..."
docker compose up -d --build app worker

log "Waiting for app readiness on $BASE_URL..."
wait_for_app || fail "App did not become ready within ${STARTUP_TIMEOUT_SECONDS}s"

log "Logging in with bootstrap credentials..."
status_code="$(post_login "$ADMIN_USERNAME" "$BOOTSTRAP_PASSWORD" "$tmp_cookie" "$tmp_headers" "$tmp_body")"
location="$(extract_location "$tmp_headers")"
if [[ "$status_code" != "303" || "$location" != "/admin/change-password?notice=default" ]]; then
  fail "Bootstrap login failed. status=$status_code location='$location'"
fi

log "Changing admin password..."
status_code="$(
  curl -sS \
    -o "$tmp_body" \
    -D "$tmp_headers" \
    -c "$tmp_cookie" \
    -b "$tmp_cookie" \
    -w "%{http_code}" \
    -X POST "$BASE_URL/admin/change-password" \
    --data-urlencode "old_password=$BOOTSTRAP_PASSWORD" \
    --data-urlencode "new_password=$NEW_PASSWORD" \
    --data-urlencode "confirm_password=$NEW_PASSWORD"
)"
if [[ "$status_code" != "200" ]]; then
  fail "Password change request failed. status=$status_code"
fi
if ! grep -q "Password updated successfully" "$tmp_body"; then
  fail "Password change did not report success."
fi

log "Verifying old password is rejected..."
status_code="$(post_login "$ADMIN_USERNAME" "$BOOTSTRAP_PASSWORD" "$tmp_cookie" "$tmp_headers" "$tmp_body")"
if [[ "$status_code" != "200" ]]; then
  fail "Expected old password attempt to return 200 with error, got $status_code"
fi
if ! grep -q "Invalid credentials" "$tmp_body"; then
  fail "Old password was not rejected as expected."
fi

log "Verifying new password works..."
status_code="$(post_login "$ADMIN_USERNAME" "$NEW_PASSWORD" "$tmp_cookie" "$tmp_headers" "$tmp_body")"
location="$(extract_location "$tmp_headers")"
if [[ "$status_code" != "303" || "$location" != "/embeddings" ]]; then
  fail "New password login failed. status=$status_code location='$location'"
fi

log "Restarting app service (without wiping volumes)..."
docker compose restart app
wait_for_app || fail "App did not become ready after restart within ${STARTUP_TIMEOUT_SECONDS}s"

log "Re-validating credentials after restart..."
status_code="$(post_login "$ADMIN_USERNAME" "$NEW_PASSWORD" "$tmp_cookie" "$tmp_headers" "$tmp_body")"
location="$(extract_location "$tmp_headers")"
if [[ "$status_code" != "303" || "$location" != "/embeddings" ]]; then
  fail "New password failed after restart. status=$status_code location='$location'"
fi

status_code="$(post_login "$ADMIN_USERNAME" "$BOOTSTRAP_PASSWORD" "$tmp_cookie" "$tmp_headers" "$tmp_body")"
if [[ "$status_code" != "200" ]] || ! grep -q "Invalid credentials" "$tmp_body"; then
  fail "Old password unexpectedly accepted after restart."
fi

log "PASS: password persistence behavior is healthy."
