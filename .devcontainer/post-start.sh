#!/usr/bin/env bash
# Runs every time the codespace starts (postStartCommand), including after it was
# stopped. A stopped codespace loses all running processes, so Ollama has to be
# started again each time (test log pitfall #7).
#
#   1. start Ollama in the background on 0.0.0.0 (unless it is already running)
#   2. wait until it answers, pull the models from .env if missing
#   3. docker compose up -d (COMPOSE_FILE adds docker-compose.codespaces.yml)
#   4. index the sample project if Qdrant has no index yet
#   5. run scripts/doctor.sh and print the URL
#
# Output is also appended to .logs/post-start.log. Run it again by hand any time:
#   bash .devcontainer/post-start.sh
set -uo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR" || exit 1
mkdir -p .logs
exec > >(tee -a .logs/post-start.log) 2>&1

step() { echo; echo "==> [$(date +%H:%M:%S)] $*"; }
warn() { echo "!  $*"; }
die()  { echo "✗  $*"; echo "   Run ./scripts/doctor.sh for a step-by-step diagnosis."; exit 1; }

# Fallback for shells that do not get containerEnv (e.g. running this by hand elsewhere).
export COMPOSE_FILE="${COMPOSE_FILE:-$ROOT_DIR/docker-compose.yml:$ROOT_DIR/docker-compose.codespaces.yml}"
[ -f .env ] || cp .env.codespaces .env
set -a
# shellcheck disable=SC1091
. ./.env
set +a
LLM_MODEL="${LLM_MODEL:-qwen2.5-coder:3b}"
EMBED_MODEL="${EMBED_MODEL:-nomic-embed-text}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-8080}"

ollama_up() { curl -sS --max-time 3 http://127.0.0.1:11434/api/version >/dev/null 2>&1; }

# ── 1. Ollama ─────────────────────────────────────────────────────────────
step "Starting Ollama on 0.0.0.0:11434"
command -v ollama >/dev/null 2>&1 || die "ollama is not installed (post-create did not finish?). Run: bash .devcontainer/post-create.sh"
if ollama_up; then
  echo "already running"
else
  # 0.0.0.0, not the default 127.0.0.1: containers come in through the Docker
  # bridge gateway, not loopback. >> keeps the log of earlier starts.
  OLLAMA_HOST=0.0.0.0 nohup ollama serve >> .logs/ollama.log 2>&1 &
  echo "started (pid $!), log: .logs/ollama.log"
fi
for _ in $(seq 1 60); do ollama_up && break; sleep 1; done
ollama_up || die "Ollama did not answer within 60 s. See .logs/ollama.log"
echo "Ollama $(curl -sS http://127.0.0.1:11434/api/version)"

# ── 2. Models ─────────────────────────────────────────────────────────────
step "Models: $LLM_MODEL, $EMBED_MODEL"
for model in "$LLM_MODEL" "$EMBED_MODEL"; do
  if ollama show "$model" >/dev/null 2>&1; then
    echo "$model: present"
  else
    echo "$model: pulling (the first time takes a few minutes)"
    ollama pull "$model" || die "could not pull $model"
  fi
done

# ── 3. Stack ──────────────────────────────────────────────────────────────
step "Waiting for Docker"
for _ in $(seq 1 60); do docker info >/dev/null 2>&1 && break; sleep 1; done
docker info >/dev/null 2>&1 || die "Docker is not running"

step "docker compose up -d --build (COMPOSE_FILE=$COMPOSE_FILE)"
# --build is quick when nothing changed (layer cache) and picks up a git pull.
docker compose up -d --build || die "docker compose up failed. See: docker compose logs"

step "Waiting for the backend"
health=""
for _ in $(seq 1 90); do
  health="$(curl -sS --max-time 5 "http://127.0.0.1:${BACKEND_PORT}/health" 2>/dev/null)" && break
  sleep 2
done
[ -n "$health" ] || die "the backend did not answer within 3 minutes. See: docker compose logs backend"

# ── 4. Index if empty ─────────────────────────────────────────────────────
if [ "$(jq -r '.qdrant.indexed' <<<"$health" 2>/dev/null)" = "true" ]; then
  echo "index present: $(jq -r '.qdrant.points' <<<"$health") chunks"
elif [ "$(jq -r '.status' <<<"$health" 2>/dev/null)" = "ok" ]; then
  step "No index yet: indexing $(jq -r '.codebase_path' <<<"$health")"
  ./scripts/index.sh || warn "indexing failed; try ./scripts/index.sh again"
else
  warn "the backend reports status=$(jq -r '.status' <<<"$health" 2>/dev/null); skipping indexing"
fi

# ── 5. Doctor ─────────────────────────────────────────────────────────────
step "Health check (scripts/doctor.sh)"
./scripts/doctor.sh || warn "some checks failed: see the fixes above"

echo
if [ "${CODESPACES:-}" = "true" ] && [ -n "${CODESPACE_NAME:-}" ]; then
  echo "Ready: https://${CODESPACE_NAME}-${FRONTEND_PORT}.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
  echo "(or open port ${FRONTEND_PORT} in the Ports panel)"
else
  echo "Ready: http://localhost:${FRONTEND_PORT}"
fi
