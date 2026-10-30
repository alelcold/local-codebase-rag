#!/usr/bin/env bash
# 一鍵安裝/啟動：檢查 Ollama → 拉取模型 → 啟動 docker compose →（可選）建立索引。
#
# 用法：
#   ./scripts/setup.sh              # 檢查、拉模型、啟動服務
#   ./scripts/setup.sh --index      # 同上，並在啟動後建立索引
#   ./scripts/setup.sh --skip-pull  # 不檢查/拉取模型
#   ./scripts/setup.sh --no-build   # 不重新 build 映像
#
# 相容 macOS 內建的 bash 3.2。
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

DO_INDEX=0
DO_PULL=1
BUILD_FLAG="--build"
for arg in "$@"; do
  case "$arg" in
    --index) DO_INDEX=1 ;;
    --skip-pull) DO_PULL=0 ;;
    --no-build) BUILD_FLAG="" ;;
    -h|--help) sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "未知參數：$arg（用 --help 查看說明）" >&2; exit 2 ;;
  esac
done

if [ -t 1 ]; then
  BOLD=$'\033[1m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RED=$'\033[31m'; RESET=$'\033[0m'
else
  BOLD=""; GREEN=""; YELLOW=""; RED=""; RESET=""
fi
step() { echo; echo "${BOLD}==> $*${RESET}"; }
ok()   { echo "${GREEN}✓${RESET} $*"; }
warn() { echo "${YELLOW}!${RESET} $*"; }
fail() { echo "${RED}✗ $*${RESET}" >&2; exit 1; }

# ── 1. 環境檢查 ────────────────────────────────────────────────
step "檢查系統"
OS="$(uname -s)"; ARCH="$(uname -m)"
if [ "$OS" = "Darwin" ] && [ "$ARCH" = "arm64" ]; then
  ok "macOS Apple Silicon（$ARCH）"
else
  warn "目前是 $OS/$ARCH。本專案以 Apple Silicon Mac 為目標，其他平台可運作但 Ollama 不會使用 Metal 加速。"
fi

# ── 2. .env ───────────────────────────────────────────────────
if [ ! -f .env ]; then
  cp .env.example .env
  ok "已從 .env.example 建立 .env（可再修改 PROJECT_PATH 等設定）"
else
  ok "使用既有的 .env"
fi
set -a
# shellcheck disable=SC1091
. ./.env
set +a

LLM_MODEL="${LLM_MODEL:-qwen2.5-coder:14b}"
EMBED_MODEL="${EMBED_MODEL:-nomic-embed-text}"
PROJECT_PATH="${PROJECT_PATH:-./examples/sample-game-frontend}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-8080}"
# Mac 本機上 Ollama 的位址（容器內則是 host.docker.internal）。
OLLAMA_LOCAL_URL="${OLLAMA_LOCAL_URL:-http://127.0.0.1:11434}"

# ── 3. Ollama ─────────────────────────────────────────────────
step "檢查 Ollama（需直接安裝在 macOS 上）"
if ! command -v ollama >/dev/null 2>&1; then
  fail "找不到 ollama 指令。請先安裝：
    方法一：到 https://ollama.com/download 下載 macOS App 並開啟一次
    方法二：brew install ollama
  安裝後重新執行本腳本。請不要用 Docker 執行 Ollama（Docker 內無法使用 Metal GPU）。"
fi
ok "ollama 已安裝：$(ollama --version 2>/dev/null | head -n1)"

ollama_up() { curl -fsS --max-time 3 "$OLLAMA_LOCAL_URL/api/version" >/dev/null 2>&1; }

if ! ollama_up; then
  warn "Ollama 尚未執行，嘗試啟動…"
  if [ -d "/Applications/Ollama.app" ]; then
    open -a Ollama
  else
    mkdir -p "$ROOT_DIR/.logs"
    nohup ollama serve >"$ROOT_DIR/.logs/ollama.log" 2>&1 &
    warn "已在背景執行 ollama serve（日誌：.logs/ollama.log）。建議改用 Ollama App 或 brew services start ollama 讓它開機自動啟動。"
  fi
  for _ in $(seq 1 30); do
    ollama_up && break
    sleep 1
  done
  ollama_up || fail "等待 30 秒後仍無法連到 $OLLAMA_LOCAL_URL，請手動啟動 Ollama 後再試。"
fi
ok "Ollama 執行中：$OLLAMA_LOCAL_URL"

if [ "$DO_PULL" -eq 1 ]; then
  step "準備模型"
  for model in "$LLM_MODEL" "$EMBED_MODEL"; do
    if ollama show "$model" >/dev/null 2>&1; then
      ok "$model 已存在"
    else
      echo "下載 $model（14b 模型約 9GB，第一次需要一些時間）…"
      ollama pull "$model"
      ok "$model 下載完成"
    fi
  done
fi

# ── 4. Docker ─────────────────────────────────────────────────
step "檢查 Docker"
command -v docker >/dev/null 2>&1 || fail "找不到 docker。請安裝 Docker Desktop：https://www.docker.com/products/docker-desktop/"
docker info >/dev/null 2>&1 || fail "Docker 沒有在執行，請先開啟 Docker Desktop。"
docker compose version >/dev/null 2>&1 || fail "需要 Docker Compose v2（docker compose 指令）。"
ok "$(docker compose version)"

step "檢查要索引的專案"
[ -d "$PROJECT_PATH" ] || fail "PROJECT_PATH 不存在：$PROJECT_PATH（請修改 .env）"
ok "PROJECT_PATH=$PROJECT_PATH（唯讀掛載到容器的 /codebase）"

# ── 5. 啟動 ───────────────────────────────────────────────────
step "啟動服務（docker compose up -d $BUILD_FLAG）"
# shellcheck disable=SC2086
docker compose up -d $BUILD_FLAG

step "等待後端就緒"
HEALTH=""
for _ in $(seq 1 60); do
  if HEALTH="$(curl -fsS --max-time 5 "http://127.0.0.1:$BACKEND_PORT/health" 2>/dev/null)"; then
    break
  fi
  sleep 2
done
[ -n "$HEALTH" ] || fail "後端在 120 秒內沒有回應。請查看：docker compose logs backend"

if echo "$HEALTH" | grep -q '"status":"ok"'; then
  ok "後端、Qdrant、Ollama 都正常"
else
  warn "後端已啟動，但健康檢查回報異常："
  echo "$HEALTH"
  warn "常見原因：模型尚未下載（ollama pull）、容器無法連到 Ollama。詳見 README 的「常見問題」。"
fi

if [ "$DO_INDEX" -eq 1 ]; then
  step "建立索引"
  "$ROOT_DIR/scripts/index.sh"
fi

echo
echo "${BOLD}完成！${RESET}"
echo "  查詢介面：http://localhost:$FRONTEND_PORT"
echo "  後端 API：http://localhost:$BACKEND_PORT/docs"
if [ "$DO_INDEX" -eq 0 ]; then
  echo "  建立索引：./scripts/index.sh（或在介面上按「更新索引」）"
fi
