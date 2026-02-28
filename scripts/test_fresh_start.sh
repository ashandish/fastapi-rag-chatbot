#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

BASE_URL="${BASE_URL:-http://localhost:8000}"
ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
BOOTSTRAP_PASSWORD="${BOOTSTRAP_PASSWORD:-Strongpassword123#}"
STARTUP_TIMEOUT_SECONDS="${STARTUP_TIMEOUT_SECONDS:-240}"
TMP_DOCKER_CONFIG_DIR=""

log() {
  echo "[fresh-start] $*"
}

fail() {
  echo "[fresh-start] ERROR: $*" >&2
  exit 1
}

cleanup() {
  rm -f "$tmp_cookie" "$tmp_headers" "$tmp_body"
  if [[ -n "$TMP_DOCKER_CONFIG_DIR" ]]; then
    rm -rf "$TMP_DOCKER_CONFIG_DIR"
  fi
}

ensure_docker_auth_works() {
  local config_root config_file creds_store helper
  config_root="${DOCKER_CONFIG:-$HOME/.docker}"
  config_file="$config_root/config.json"
  if [[ ! -f "$config_file" ]]; then
    return 0
  fi

  creds_store="$(python3 - "$config_file" <<'PY'
import json, os, sys
p = os.path.expanduser(os.path.expandvars(sys.argv[1]))
try:
    with open(p, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    creds_store = cfg.get("credsStore", "")
    if not creds_store:
        cred_helpers = cfg.get("credHelpers", {})
        creds_store = (
            cred_helpers.get("https://index.docker.io/v1/")
            or cred_helpers.get("index.docker.io")
            or cred_helpers.get("docker.io")
            or ""
        )
    print(creds_store)
except Exception:
    print("")
PY
)"
  if [[ -z "$creds_store" ]]; then
    return 0
  fi

  helper="docker-credential-${creds_store}"
  if ! command -v "$helper" >/dev/null 2>&1; then
    return 0
  fi

  if ! printf '%s\n' "https://index.docker.io/v1/" | "$helper" get >/dev/null 2>&1; then
    TMP_DOCKER_CONFIG_DIR="$(mktemp -d)"
    printf '{}\n' > "$TMP_DOCKER_CONFIG_DIR/config.json"
    export DOCKER_CONFIG="$TMP_DOCKER_CONFIG_DIR"
    log "Docker credential helper ($helper) failed; using temporary no-creds DOCKER_CONFIG for this run."
  fi
}

clean_data_dir() {
  mkdir -p data
  # Use a container to remove root-owned bind-mount files safely.
  docker run --rm -v "$ROOT_DIR/data:/target" alpine:3.20 sh -lc \
    'rm -rf /target/* /target/.[!.]* /target/..?* 2>/dev/null || true'
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
trap cleanup EXIT

ensure_docker_auth_works

log "Resetting stack and volumes (clean state)..."
docker compose down -v --remove-orphans || true

log "Cleaning local data directory..."
clean_data_dir

log "Starting core services (redis + ollama)..."
docker compose up -d --build redis ollama

log "Initializing Ollama model via ollama-init..."
docker compose run --rm ollama-init

log "Starting app services..."
docker compose up -d --build app worker

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
