#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

BASE_URL="${BASE_URL:-http://localhost:8000}"
ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
BOOTSTRAP_PASSWORD="${BOOTSTRAP_PASSWORD:-Strongpassword123#}"
STARTUP_TIMEOUT_SECONDS="${STARTUP_TIMEOUT_SECONDS:-240}"

log() {
  echo "[fresh-start] $*"
}

fail() {
  echo "[fresh-start] ERROR: $*" >&2
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

tmp_cookie="$(mktemp)"
tmp_headers="$(mktemp)"
tmp_body="$(mktemp)"
trap 'rm -f "$tmp_cookie" "$tmp_headers" "$tmp_body"' EXIT

log "Resetting stack and volumes (clean state)..."
docker compose down -v --remove-orphans

log "Starting services with fresh build..."
docker compose up -d --build app worker redis ollama

log "Waiting for app readiness on $BASE_URL..."
wait_for_app || fail "App did not become ready within ${STARTUP_TIMEOUT_SECONDS}s"

if [[ ! -f data/admin_hash.txt ]]; then
  fail "Expected persisted admin hash at data/admin_hash.txt"
fi
log "Found data/admin_hash.txt"

log "Validating first admin login with bootstrap password..."
status_code="$(
  curl -sS \
    -o "$tmp_body" \
    -D "$tmp_headers" \
    -c "$tmp_cookie" \
    -b "$tmp_cookie" \
    -w "%{http_code}" \
    -X POST "$BASE_URL/admin/login" \
    --data-urlencode "username=$ADMIN_USERNAME" \
    --data-urlencode "password=$BOOTSTRAP_PASSWORD"
)"
location="$(extract_location "$tmp_headers")"

if [[ "$status_code" != "303" ]]; then
  fail "Expected HTTP 303 on successful bootstrap login, got $status_code"
fi

if [[ "$location" != "/admin/change-password?notice=default" ]]; then
  fail "Expected redirect to /admin/change-password?notice=default, got '$location'"
fi

log "PASS: fresh install path is healthy."
