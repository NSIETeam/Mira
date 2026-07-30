#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_NAME="${MIRA_DOCKER_SMOKE_IMAGE:-mira:gateway-smoke}"
CONTAINER_NAME="${MIRA_DOCKER_SMOKE_CONTAINER:-mira-gateway-smoke-$$}"
GATEWAY_PORT="${MIRA_DOCKER_SMOKE_GATEWAY_PORT:-18790}"
WEBUI_PORT="${MIRA_DOCKER_SMOKE_WEBUI_PORT:-8765}"
SECRET="${MIRA_DOCKER_SMOKE_SECRET:-smoke-secret}"
BUILD_IMAGE="${MIRA_DOCKER_SMOKE_BUILD:-1}"

DATA_DIR="$(mktemp -d "${TMPDIR:-/tmp}/mira-docker-smoke.XXXXXX")"

cleanup() {
  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
  rm -rf "$DATA_DIR"
}
trap cleanup EXIT

if [[ "$BUILD_IMAGE" != "0" ]]; then
  docker build \
    --build-arg MIRA_CHANNELS=websocket \
    -t "$IMAGE_NAME" \
    "$ROOT_DIR"
fi

mkdir -p "$DATA_DIR/workspace"
cat >"$DATA_DIR/config.json" <<JSON
{
  "providers": {
    "smoke": {
      "apiBase": "http://127.0.0.1:9/v1",
      "apiKey": "smoke"
    }
  },
  "modelPresets": {
    "smoke": {
      "provider": "smoke",
      "model": "smoke-model",
      "maxTokens": 128,
      "contextWindowTokens": 4096
    }
  },
  "agents": {
    "defaults": {
      "workspace": "/home/mira/.mira/workspace",
      "modelPreset": "smoke",
      "dream": {
        "enabled": false
      }
    }
  },
  "gateway": {
    "host": "0.0.0.0",
    "port": 18790,
    "heartbeat": {
      "enabled": false
    }
  },
  "channels": {
    "websocket": {
      "enabled": true,
      "host": "0.0.0.0",
      "port": 8765,
      "path": "/ws",
      "allowFrom": ["*"],
      "tokenIssueSecret": "$SECRET",
      "websocketRequiresToken": true
    }
  }
}
JSON

docker run \
  --name "$CONTAINER_NAME" \
  -d \
  -v "$DATA_DIR:/home/mira/.mira" \
  -p "127.0.0.1:${GATEWAY_PORT}:18790" \
  -p "127.0.0.1:${WEBUI_PORT}:8765" \
  "$IMAGE_NAME" \
  gateway --config /home/mira/.mira/config.json >/dev/null

wait_for_url() {
  local label="$1"
  local url="$2"
  shift 2
  local deadline=$((SECONDS + 45))
  until curl -fsS "$@" "$url" >/tmp/mira-docker-smoke-response 2>/tmp/mira-docker-smoke-curl; do
    if (( SECONDS >= deadline )); then
      echo "Docker smoke failed waiting for ${label}: ${url}" >&2
      echo "--- container logs ---" >&2
      docker logs "$CONTAINER_NAME" >&2 || true
      echo "--- curl error ---" >&2
      cat /tmp/mira-docker-smoke-curl >&2 || true
      return 1
    fi
    sleep 1
  done
}

wait_for_url "gateway health" "http://127.0.0.1:${GATEWAY_PORT}/health"
grep -q '"status": "ok"' /tmp/mira-docker-smoke-response

wait_for_url "webui bootstrap" "http://127.0.0.1:${WEBUI_PORT}/webui/bootstrap" \
  -H "X-mira-Auth: ${SECRET}"
grep -q '"token"' /tmp/mira-docker-smoke-response
grep -q '"api_token"' /tmp/mira-docker-smoke-response

wait_for_url "webui index" "http://127.0.0.1:${WEBUI_PORT}/"
grep -Eq '<div id="root"|/assets/' /tmp/mira-docker-smoke-response

docker exec "$CONTAINER_NAME" sh -lc \
  'test -f /app/mira/web/dist/index.html && test -d /app/.venv && test "$(id -u)" != "0"'

echo "Docker gateway smoke passed: gateway=${GATEWAY_PORT} webui=${WEBUI_PORT}"
