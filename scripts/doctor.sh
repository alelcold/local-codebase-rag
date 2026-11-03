#!/usr/bin/env bash
# 環境診斷：依序檢查 Ollama → Docker → 各服務 → 索引，並針對失敗項目印出修正指令。
# Diagnose the stack step by step and print the fix for anything that fails.
#
#   ./scripts/doctor.sh
#
# 檢查順序（前面失敗時，後面依賴它的項目會略過）：
#   1. Ollama 已安裝         2. Ollama 程序在執行      3. Ollama API 有回應
#   4. 監聽位址（Linux 需 0.0.0.0）                     5. 模型已下載
#   6. Docker 在執行         7. 容器都在執行           8. 容器連得到 Ollama
#   9. 後端 /health          10. 前端與 nginx 代理     11. Qdrant 已有索引
#  12. Git LFS hook 有對應的 git-lfs（否則 git push 會失敗；與服務無關，最後檢查）
#
# 把 Codespaces 測試紀錄踩坑 #1～#7 的手動排查步驟自動化
# （devlog 2026-11-01、docs/devlog/2026-11-01-codespace-setup.md）。
# 只讀取狀態，不會修改任何東西。相容 macOS 內建的 bash 3.2。
# Exit code: 0 when every check passes, 1 otherwise.
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR" || exit 1

if [ -t 1 ]; then
  BOLD=$'\033[1m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RED=$'\033[31m'; DIM=$'\033[2m'; RESET=$'\033[0m'
else
  BOLD=""; GREEN=""; YELLOW=""; RED=""; DIM=""; RESET=""
fi

FAILED=0
WARNED=0
N=0
check() { N=$((N + 1)); printf '%s%2d. %s%s\n' "$BOLD" "$N" "$*" "$RESET"; }
ok()    { echo "    ${GREEN}✓${RESET} $*"; }
warn()  { echo "    ${YELLOW}!${RESET} $*"; WARNED=$((WARNED + 1)); }
bad()   { echo "    ${RED}✗${RESET} $*"; FAILED=$((FAILED + 1)); }
skip()  { echo "    ${DIM}- 略過：$*${RESET}"; }
# Indented fix commands, one per argument.
fix()   { echo "    修正："; for line in "$@"; do echo "      $line"; done; }

# JSON field via jq, or python3 when jq is missing (macOS). $1 = JSON, $2 = path like .qdrant.points
json() {
  if command -v jq >/dev/null 2>&1; then
    jq -r "$2 // empty" <<<"$1" 2>/dev/null
  else
    python3 -c '
import json, sys
value = json.loads(sys.argv[1])
for key in sys.argv[2].strip(".").split("."):
    value = value.get(key) if isinstance(value, dict) else None
print("" if value is None else (str(value).lower() if isinstance(value, bool) else value))
' "$1" "$2" 2>/dev/null
  fi
}

# Settings: .env if present, then defaults (same as docker-compose.yml).
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi
LLM_MODEL="${LLM_MODEL:-qwen2.5-coder:14b}"
EMBED_MODEL="${EMBED_MODEL:-nomic-embed-text}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-8080}"
OLLAMA_LOCAL_URL="${OLLAMA_LOCAL_URL:-http://127.0.0.1:11434}"
OS="$(uname -s)"
OLLAMA_LOG=".logs/ollama.log"
START_OLLAMA="mkdir -p .logs && OLLAMA_HOST=0.0.0.0 nohup ollama serve >> $OLLAMA_LOG 2>&1 &"
[ "$OS" = "Darwin" ] && START_OLLAMA="open -a Ollama   # 或：brew services start ollama"

echo "${BOLD}local-codebase-rag doctor${RESET}  ${DIM}($OS, LLM_MODEL=$LLM_MODEL, EMBED_MODEL=$EMBED_MODEL${COMPOSE_FILE:+, COMPOSE_FILE set})${RESET}"
echo

# ── 1. Ollama installed ───────────────────────────────────────────────────
check "Ollama 已安裝"
OLLAMA_INSTALLED=0
if command -v ollama >/dev/null 2>&1; then
  ok "$(ollama --version 2>/dev/null | head -n1)"
  OLLAMA_INSTALLED=1
else
  bad "找不到 ollama 指令"
  if [ "$OS" = "Darwin" ]; then
    fix "brew install ollama   # 或到 https://ollama.com/download 下載 App"
  else
    fix "curl -fsSL https://ollama.com/install.sh | sh"
  fi
fi

# ── 2. Ollama process (pitfalls #1, #7: not running, or gone after a restart) ──
check "Ollama 程序在執行"
OLLAMA_PROC=0
# By exact process name (`ollama serve` runs as "ollama"; the macOS app as "Ollama"),
# so shells whose command line merely mentions ollama do not count.
pid="$(pgrep -x ollama 2>/dev/null | head -n1)"
[ -n "$pid" ] || pid="$(pgrep -x Ollama 2>/dev/null | head -n1)"
if [ -n "$pid" ]; then
  ok "pid $pid"
  OLLAMA_PROC=1
elif [ "$OLLAMA_INSTALLED" = 1 ]; then
  bad "沒有在執行的 ollama serve（Codespace 停止後重開，背景程序都會消失）"
  fix "$START_OLLAMA" "# 在背景執行（結尾的 &），用 >> 附加 log，不會蓋掉之前的紀錄"
else
  skip "Ollama 尚未安裝"
fi

# ── 3. Ollama API (pitfall #3: curl -sS shows the error instead of hiding it) ──
check "Ollama API 有回應（$OLLAMA_LOCAL_URL）"
OLLAMA_API=0
if out="$(curl -sS --max-time 5 "$OLLAMA_LOCAL_URL/api/version" 2>&1)"; then
  ok "$out"
  OLLAMA_API=1
elif [ "$OLLAMA_PROC" = 1 ]; then
  bad "程序在執行，但 API 沒有回應：$out"
  fix "tail -n 30 $OLLAMA_LOG   # 看啟動錯誤，例如 address already in use" \
      "ss -ltnp | grep 11434     # 是否有其他程序佔用 11434"
else
  bad "連不到：$out"
  [ "$OLLAMA_INSTALLED" = 1 ] && fix "$START_OLLAMA"
fi

# ── 4. Listening address (pitfall #4/#5: 127.0.0.1 is unreachable from containers on Linux) ──
check "Ollama 監聽位址"
listen=""
if command -v ss >/dev/null 2>&1; then
  listen="$(ss -ltnH 2>/dev/null | awk '{print $4}' | grep -E ':11434$' | sort -u | tr '\n' ' ')"
elif command -v lsof >/dev/null 2>&1; then
  listen="$(lsof -nP -iTCP:11434 -sTCP:LISTEN 2>/dev/null | awk 'NR > 1 {print $9}' | sort -u | tr '\n' ' ')"
fi
listen="${listen% }"
if [ -z "$listen" ]; then
  if [ "$OLLAMA_API" = 1 ]; then warn "無法判斷（沒有 ss / lsof）"; else skip "沒有程序監聽 11434"; fi
elif echo "$listen" | grep -Eq '(^| )(0\.0\.0\.0|\*|\[::\]|::):11434'; then
  ok "$listen（容器可以經由 Docker bridge 連進來）"
elif [ "$OS" = "Darwin" ]; then
  ok "$listen（macOS 的 Docker Desktop 會把 host.docker.internal 轉到主機的 127.0.0.1，不需要 0.0.0.0）"
else
  bad "只監聽 $listen：容器是從 Docker bridge gateway 連過來的，連不到 127.0.0.1"
  fix "pkill -x ollama; sleep 1" "$START_OLLAMA"
fi

# ── 5. Models ─────────────────────────────────────────────────────────────
check "模型已下載（$LLM_MODEL、$EMBED_MODEL）"
if [ "$OLLAMA_API" = 1 ]; then
  tags="$(curl -sS --max-time 5 "$OLLAMA_LOCAL_URL/api/tags" 2>/dev/null)"
  for model in "$LLM_MODEL" "$EMBED_MODEL"; do
    case "$model" in *:*) want="$model" ;; *) want="$model:latest" ;; esac
    if grep -q "\"name\":\"$want\"" <<<"$(tr -d ' ' <<<"$tags")"; then
      ok "$model"
    else
      bad "缺少 $model"
      fix "ollama pull $model"
    fi
  done
else
  skip "Ollama API 沒有回應"
fi

# ── 6. Docker ─────────────────────────────────────────────────────────────
check "Docker 在執行"
DOCKER=0
if ! command -v docker >/dev/null 2>&1; then
  bad "找不到 docker 指令"
  fix "安裝 Docker Desktop（Mac）或 Docker Engine（Linux）"
elif ! docker info >/dev/null 2>&1; then
  bad "Docker daemon 沒有回應"
  if [ "${CODESPACES:-}" = "true" ]; then
    fix "# docker-in-docker 剛啟動時需要幾秒；稍候再試，或 Rebuild Container"
  else
    fix "開啟 Docker Desktop（Mac），或 sudo systemctl start docker（Linux）"
  fi
else
  ok "$(docker compose version 2>/dev/null)"
  DOCKER=1
fi

# ── 7. Containers ─────────────────────────────────────────────────────────
check "容器都在執行（qdrant、backend、frontend）"
BACKEND_RUNNING=0
if [ "$DOCKER" = 1 ]; then
  running=" $(docker compose ps --status running --services 2>/dev/null | tr '\n' ' ') "
  missing=""
  for svc in qdrant backend frontend; do
    case "$running" in *" $svc "*) ;; *) missing="$missing $svc" ;; esac
  done
  case "$running" in *" backend "*) BACKEND_RUNNING=1 ;; esac
  if [ -z "$missing" ]; then
    ok "${running# }"
  else
    bad "沒有在執行：${missing# }"
    fix "docker compose up -d" "docker compose ps -a              # 看狀態與結束代碼" \
        "docker compose logs --tail 50${missing}"
  fi
else
  skip "Docker 沒有在執行"
fi

# ── 8. Container → Ollama (pitfall #4: test from where the caller is) ─────
check "容器連得到 Ollama（從 backend 容器呼叫 host.docker.internal:11434）"
if [ "$BACKEND_RUNNING" = 1 ]; then
  if out="$(docker compose exec -T backend python -c \
      "import os, urllib.request; print(urllib.request.urlopen(os.environ.get('OLLAMA_BASE_URL', 'http://host.docker.internal:11434') + '/api/version', timeout=5).read().decode())" 2>&1)"; then
    ok "$out"
  else
    bad "連不到：$(tail -n1 <<<"$out")"
    if [ "$OS" = "Darwin" ]; then
      fix "確認 Ollama 在 Mac 上執行中（第 2～3 項），並確認 .env 的 OLLAMA_BASE_URL"
    else
      fix "# 1) Ollama 要監聽 0.0.0.0（第 4 項）" \
          "# 2) backend 要有 extra_hosts: host.docker.internal:host-gateway：" \
          "docker compose config | grep -A1 extra_hosts" \
          "# 3) 用一次性的容器直接測試：" \
          "docker run --rm --add-host=host.docker.internal:host-gateway curlimages/curl -sS http://host.docker.internal:11434/api/version"
    fi
  fi
else
  skip "backend 容器沒有在執行"
fi

# ── 9. Backend /health ────────────────────────────────────────────────────
check "後端 /health（http://127.0.0.1:$BACKEND_PORT）"
HEALTH=""
out="$(curl -sS --max-time 10 "http://127.0.0.1:$BACKEND_PORT/health" 2>&1)"
if [ -n "$(json "$out" .status)" ]; then
  HEALTH="$out"
  status="$(json "$HEALTH" .status)"
  if [ "$status" = "ok" ]; then
    ok "status=ok（Ollama 與 Qdrant 都正常）"
  else
    bad "status=$status"
    [ "$(json "$HEALTH" .ollama.ok)" = "true" ] || echo "      ollama：$(json "$HEALTH" .ollama.error)$(json "$HEALTH" .ollama.missing_models)"
    [ "$(json "$HEALTH" .qdrant.ok)" = "true" ] || echo "      qdrant：$(json "$HEALTH" .qdrant.error)"
    fix "# 先修正上面第 2～8 項的失敗，再執行：" "docker compose restart backend"
  fi
else
  bad "沒有回應：$(tail -n1 <<<"$out")"
  fix "docker compose logs --tail 50 backend"
fi

# ── 10. Frontend and nginx proxy ──────────────────────────────────────────
check "前端與 nginx 代理（http://127.0.0.1:$FRONTEND_PORT）"
code="$(curl -sS --max-time 10 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$FRONTEND_PORT/" 2>/dev/null)"
if [ "$code" = "200" ]; then
  api_code="$(curl -sS --max-time 10 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$FRONTEND_PORT/api/health" 2>/dev/null)"
  if [ "$api_code" = "200" ]; then
    ok "介面 200，/api/health 經 nginx 代理 200"
  else
    bad "介面 200，但 /api/health 回傳 ${api_code:-無回應}（nginx 連不到 backend）"
    fix "docker compose logs --tail 50 frontend"
  fi
else
  bad "介面回傳 ${code:-無回應}"
  fix "docker compose up -d frontend" "docker compose logs --tail 50 frontend"
fi

# ── 11. Qdrant index ──────────────────────────────────────────────────────
check "Qdrant 已有索引"
if [ -n "$HEALTH" ] && [ "$(json "$HEALTH" .qdrant.ok)" = "true" ]; then
  if [ "$(json "$HEALTH" .qdrant.indexed)" = "true" ] && [ "$(json "$HEALTH" .qdrant.points)" != "0" ]; then
    ok "collection $(json "$HEALTH" .qdrant.collection)：$(json "$HEALTH" .qdrant.points) 個片段（$(json "$HEALTH" .codebase_path)）"
  else
    bad "collection $(json "$HEALTH" .qdrant.collection) 還沒有資料"
    fix "./scripts/index.sh        # 或在介面按「更新索引」"
  fi
else
  skip "後端或 Qdrant 沒有回應"
fi

# ── 12. Git LFS (independent of the stack: a hook without git-lfs blocks git push) ──
check "Git LFS（git push 用）"
if hooks="$(git rev-parse --git-path hooks 2>/dev/null)"; then
  lfs_hooks=""
  for h in pre-push post-checkout post-commit post-merge; do
    [ -f "$hooks/$h" ] && grep -q 'git[- ]lfs' "$hooks/$h" 2>/dev/null && lfs_hooks="$lfs_hooks $h"
  done
  if command -v git-lfs >/dev/null 2>&1; then
    ok "$(git lfs version 2>/dev/null | head -n1)${lfs_hooks:+（hook：${lfs_hooks# }）}"
  elif [ -n "$lfs_hooks" ]; then
    bad "$hooks 有 Git LFS 的 hook（${lfs_hooks# }），但沒有安裝 git-lfs：git push 會失敗"
    if [ "$OS" = "Darwin" ]; then
      fix "brew install git-lfs"
    else
      fix "sudo apt-get update && sudo apt-get install -y git-lfs   # dev container 的 post-create.sh 已包含"
    fi
    echo "      ${DIM}# 本專案沒有用 LFS 管理的檔案；也可以改成刪除 hook：rm$(for h in $lfs_hooks; do printf ' %s' "$hooks/$h"; done)${RESET}"
  else
    ok "沒有 Git LFS hook，不需要 git-lfs"
  fi
else
  skip "不是 git repo"
fi

# ── Summary ───────────────────────────────────────────────────────────────
echo
if [ "$FAILED" -eq 0 ]; then
  if [ "$WARNED" -gt 0 ]; then extra="，警告 $WARNED"; else extra=""; fi
  echo "${GREEN}${BOLD}全部通過${RESET}（$N 項$extra）"
  if [ "${CODESPACES:-}" = "true" ] && [ -n "${CODESPACE_NAME:-}" ]; then
    echo "介面：https://${CODESPACE_NAME}-${FRONTEND_PORT}.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
  else
    echo "介面：http://localhost:$FRONTEND_PORT"
  fi
  exit 0
fi
echo "${RED}${BOLD}$FAILED 項失敗${RESET}：從第一個 ✗ 開始修正，後面的項目常常會跟著恢復。修正後再執行 ./scripts/doctor.sh"
[ -f "$OLLAMA_LOG" ] && echo "${DIM}Ollama log：$OLLAMA_LOG${RESET}"
exit 1
