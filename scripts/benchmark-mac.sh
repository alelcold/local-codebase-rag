#!/usr/bin/env bash
# Mac 實機一鍵測試：Ollama（Metal）→ 生成速度與記憶體 → 索引計時 → 檢索實驗 → 摘要 Markdown。
# One-command benchmark on an Apple Silicon Mac (target: M2, 32 GB, qwen2.5-coder:14b).
#
# 用法：
#   ./scripts/benchmark-mac.sh                # 完整測試（約 30–60 分鐘，視機型而定）
#   ./scripts/benchmark-mac.sh --skip-pull    # 不拉模型（模型必須已經存在）
#   ./scripts/benchmark-mac.sh --quick        # 每個題組只跑 3 題，用來先確認流程（結果寫到 .logs/）
#   ./scripts/benchmark-mac.sh --with-rerank  # 另跑 Rerank 組（會以 INSTALL_RERANK=true build backend，映像檔多約 1.5 GB）
#
# 步驟（ADR 0016）：
#   1. 確認是 Apple Silicon、.env 的 PROJECT_PATH 是範例專案、Docker 在執行
#   2. 確認 Ollama 直接安裝在 macOS 上並在執行，拉取 qwen2.5-coder:14b 與 embedding 模型
#   3. ollama run --verbose：冷啟動與暖機後的 prompt eval rate / eval rate；ollama ps 確認 100% GPU（Metal）
#   4. build 並啟動服務，計時全量索引（--full）與無變更的增量索引
#   5. 依 docs/evaluation/experiment-plan-retrieval.md，以 TOP_K=8 跑兩組（主要題組＋識別字題組）：
#        baseline       全部關閉
#        hybrid-split   HYBRID_SEARCH=true SPLIT_RETRIEVAL=true DOC_TOP_K=1
#        hybrid-split-rerank（--with-rerank）  同上 + RERANK=true RERANK_CANDIDATES=20 RERANK_TOP_N=8
#      label 為 mac-m2-14b-k8-<組別>；每組先檢查 /health 的設定，每次評估前卸載模型（避免跨組的提示快取）
#   6. compare.py 比較各組，輸出摘要 Markdown（欄位對齊 docs/metrics.md §2、§3、§4、§4a、§5）
#   7. 把 backend 恢復成 .env 的設定
#
# 開關只用 shell 環境變數傳給 docker compose，不會修改 .env。相容 macOS 內建的 bash 3.2。
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

DO_PULL=1
QUICK=0
WITH_RERANK=0
for arg in "$@"; do
  case "$arg" in
    --skip-pull) DO_PULL=0 ;;
    --quick) QUICK=1 ;;
    --with-rerank) WITH_RERANK=1 ;;
    -h|--help) sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "未知參數：$arg（用 --help 查看說明）" >&2; exit 2 ;;
  esac
done

if [ -t 1 ]; then
  BOLD=$'\033[1m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RED=$'\033[31m'; DIM=$'\033[2m'; RESET=$'\033[0m'
else
  BOLD=""; GREEN=""; YELLOW=""; RED=""; DIM=""; RESET=""
fi
step() { echo; echo "${BOLD}==> $*${RESET}"; }
ok()   { echo "${GREEN}✓${RESET} $*"; }
warn() { echo "${YELLOW}!${RESET} $*"; }
fail() { echo "${RED}✗ $*${RESET}" >&2; exit 1; }

# ── Fixed conditions of this benchmark ────────────────────────────────────
LLM="qwen2.5-coder:14b"
BENCH_TOP_K=8
PREFIX="mac-m2-14b-k8"
RERANK_CANDIDATES_BENCH=20   # 20 → 8 keeps the 2.5× ratio of the Codespaces runs (10 → 4)
QUICK_MAIN="1,4,10"          # 定位設定、跨檔案流程、陷阱題
QUICK_IDENT="11,12,13"
# (Not "GROUPS": that is a read-only bash variable.)
BENCH_GROUP_LIST="baseline hybrid-split"
[ "$WITH_RERANK" = 1 ] && BENCH_GROUP_LIST="$BENCH_GROUP_LIST hybrid-split-rerank"

STAMP="$(date +%Y%m%d-%H%M%S)"
LOG_DIR=".logs/benchmark-$STAMP"
mkdir -p "$LOG_DIR"
if [ "$QUICK" = 1 ]; then
  OUT_DIR="$LOG_DIR/results"   # partial runs never land in docs/
else
  OUT_DIR="docs/evaluation/results"
fi
mkdir -p "$OUT_DIR"
# Everything printed from here on is also kept in the log.
exec > >(tee -a "$LOG_DIR/benchmark.log") 2>&1

# Value from .env without exporting it (so group settings below are the only overrides).
env_get() {
  (
    # shellcheck disable=SC1091
    if [ -f .env ]; then set -a; . ./.env >/dev/null 2>&1; set +a; fi
    eval "printf '%s' \"\${$1:-}\""
  )
}
now() { python3 -c 'import time; print("%.3f" % time.time())'; }
since() { awk -v a="$1" -v b="$(now)" 'BEGIN { printf "%.2f", b - a }'; }

EMBED_MODEL="$(env_get EMBED_MODEL)"; EMBED_MODEL="${EMBED_MODEL:-nomic-embed-text}"
PROJECT_PATH="$(env_get PROJECT_PATH)"; PROJECT_PATH="${PROJECT_PATH:-./examples/sample-game-frontend}"
BACKEND_PORT="$(env_get BACKEND_PORT)"; BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="$(env_get FRONTEND_PORT)"; FRONTEND_PORT="${FRONTEND_PORT:-8080}"
LLM_NUM_CTX="$(env_get LLM_NUM_CTX)"; LLM_NUM_CTX="${LLM_NUM_CTX:-16384}"
OLLAMA_LOCAL_URL="${OLLAMA_LOCAL_URL:-http://127.0.0.1:11434}"
HEALTH_URL="http://127.0.0.1:$BACKEND_PORT/health"
BASE_URL="http://localhost:$FRONTEND_PORT/api"

STACK_TOUCHED=0
restore_backend() {
  if [ "$STACK_TOUCHED" = 1 ]; then
    echo
    echo "${DIM}恢復 backend 為 .env 的設定：docker compose up -d backend${RESET}"
    docker compose up -d --wait backend >/dev/null 2>&1 || warn "恢復失敗，請手動執行：docker compose up -d backend"
    STACK_TOUCHED=0
  fi
}
on_exit() {
  rc=$?
  restore_backend
  if [ "$rc" -ne 0 ]; then
    echo "${RED}中止（exit $rc）。${RESET}完整紀錄：$LOG_DIR/benchmark.log"
  fi
}
trap on_exit EXIT

echo "${BOLD}local-codebase-rag Mac benchmark${RESET}  ${DIM}($STAMP, quick=$QUICK, rerank=$WITH_RERANK, pull=$DO_PULL)${RESET}"
echo "${DIM}log: $LOG_DIR/benchmark.log${RESET}"

# ── 1. Machine, project, Docker ───────────────────────────────────────────
step "1. 檢查機器、專案與 Docker"
OS="$(uname -s)"; ARCH="$(uname -m)"
[ "$OS" = "Darwin" ] && [ "$ARCH" = "arm64" ] || fail "需要 Apple Silicon Mac（目前是 $OS/$ARCH）。其他環境請改用 scripts/evaluate.py，並使用不同的 label。"
CHIP="$(sysctl -n machdep.cpu.brand_string 2>/dev/null || echo unknown)"
MEM_GB="$(sysctl -n hw.memsize 2>/dev/null | awk '{ printf "%d", $1 / 1073741824 }')"
MACOS="$(sw_vers -productVersion 2>/dev/null || echo unknown)"
ok "$CHIP、${MEM_GB} GB、macOS $MACOS"
case "$CHIP" in
  *M2*) ;;
  *) warn "晶片不是 M2，但 label 固定為 $PREFIX-*；記錄到 docs/metrics.md 時請註明實際機型" ;;
esac

SAMPLE_ABS="$(cd examples/sample-game-frontend && pwd -P)"
PROJECT_ABS="$(cd "$PROJECT_PATH" 2>/dev/null && pwd -P || echo "$PROJECT_PATH")"
if [ "$PROJECT_ABS" != "$SAMPLE_ABS" ]; then
  fail ".env 的 PROJECT_PATH 指向 $PROJECT_PATH，不是範例專案。
  評估題目只適用於 examples/sample-game-frontend/，結果也會寫進 repo（CLAUDE.md 隱私規則）；
  而且索引會覆蓋同一個 collection 中的專案。請先把 .env 改成：
    PROJECT_PATH=./examples/sample-game-frontend
  並執行 docker compose up -d，再重新執行本腳本。"
fi
ok "PROJECT_PATH 是範例專案"
[ "$EMBED_MODEL" = "nomic-embed-text" ] || warn "EMBED_MODEL=$EMBED_MODEL（Codespaces 的比較基準是 nomic-embed-text）"

command -v docker >/dev/null 2>&1 || fail "找不到 docker 指令，請安裝並開啟 Docker Desktop"
docker info >/dev/null 2>&1 || fail "Docker 沒有在執行，請開啟 Docker Desktop"
ok "$(docker compose version 2>/dev/null)"

# Python with PyYAML for evaluate.py (a private venv under .logs/ if the system one lacks it).
PY=python3
if ! python3 -c 'import yaml' >/dev/null 2>&1; then
  VENV=".logs/benchmark-venv"
  if [ ! -x "$VENV/bin/python" ]; then
    echo "建立 $VENV 並安裝 PyYAML（只用於評估腳本）"
    python3 -m venv "$VENV"
    "$VENV/bin/python" -m pip install --quiet -r scripts/requirements-eval.txt
  fi
  PY="$VENV/bin/python"
fi
ok "Python：$("$PY" --version 2>&1)（PyYAML 可用）"

# ── 2. Ollama on macOS, models ────────────────────────────────────────────
step "2. 檢查 Ollama 並準備模型"
command -v ollama >/dev/null 2>&1 || fail "找不到 ollama 指令。請安裝 macOS 版（brew install ollama 或 https://ollama.com/download），不要放在 Docker 裡（Docker 內無法使用 Metal）。"
if docker ps --format '{{.Image}} {{.Names}}' 2>/dev/null | grep -qi ollama; then
  warn "Docker 裡有 Ollama 容器在執行；它用不到 Metal，請停止它，避免佔用 11434 或記憶體（ADR 0002）"
fi
ollama_up() { curl -fsS --max-time 3 "$OLLAMA_LOCAL_URL/api/version" >/dev/null 2>&1; }
if ! ollama_up; then
  echo "Ollama 沒有在執行，嘗試啟動…"
  if [ -d /Applications/Ollama.app ]; then
    open -a Ollama
  elif command -v brew >/dev/null 2>&1 && brew list ollama >/dev/null 2>&1; then
    brew services start ollama >/dev/null
  else
    nohup ollama serve >> "$LOG_DIR/ollama-serve.log" 2>&1 &
  fi
  for _ in $(seq 1 30); do ollama_up && break; sleep 1; done
  ollama_up || fail "Ollama 啟動後 30 秒仍沒有回應（$OLLAMA_LOCAL_URL）"
fi
OLLAMA_VERSION="$(curl -sS "$OLLAMA_LOCAL_URL/api/version" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("version",""))')"
ok "Ollama $OLLAMA_VERSION（$OLLAMA_LOCAL_URL）"

has_model() {
  case "$1" in *:*) want="$1" ;; *) want="$1:latest" ;; esac
  ollama list 2>/dev/null | awk 'NR > 1 { print $1 }' | grep -qx "$want"
}
for model in "$LLM" "$EMBED_MODEL"; do
  if [ "$DO_PULL" = 1 ]; then
    if has_model "$model"; then
      ok "$model 已存在（ollama pull 會確認是否有更新）"
    fi
    ollama pull "$model"
  fi
  has_model "$model" || fail "缺少模型 $model（拿掉 --skip-pull，或執行 ollama pull $model）"
  ok "$model"
done
LLM_DOWNLOAD="$(ollama list | awk -v m="$LLM" '$1 == m { for (i = 3; i <= NF; i++) if ($i ~ /^[0-9.]+$/ && $(i+1) ~ /B$/) { print $i " " $(i+1); exit } }')"
ok "$LLM 下載大小：${LLM_DOWNLOAD:-unknown}（ollama list）"

# ── 3. Generation speed, memory, Metal ────────────────────────────────────
step "3. 生成速度（ollama run --verbose）與 GPU（ollama ps）"
unload() {
  # keep_alive 0 unloads the model right away (works on every Ollama version).
  curl -sS --max-time 60 "$OLLAMA_LOCAL_URL/api/generate" -d "{\"model\":\"$1\",\"keep_alive\":0}" >/dev/null 2>&1 || true
}
# Value of one --verbose statistic, e.g. "eval rate" → "21.35 tokens/s".
stat_of() {
  tr '\r' '\n' < "$1" | sed $'s/\x1b\\[[0-9;?]*[A-Za-z]//g' | grep -E "^$2:" | tail -n1 | sed -E "s/^$2:[[:space:]]*//" || true
}
SHORT_PROMPT="Explain a fixed-timestep game loop in 3 sentences."
LONG_PROMPT="Summarize what this TypeScript class does in 3 sentences.

$(cat examples/sample-game-frontend/src/entities/Player.ts)"

unload "$LLM"; unload "$EMBED_MODEL"; sleep 2
echo "冷啟動（模型從磁碟載入）：$SHORT_PROMPT"
ollama run "$LLM" --verbose "$SHORT_PROMPT" > "$LOG_DIR/ollama-run-cold.txt" 2>&1 || fail "ollama run 失敗，見 $LOG_DIR/ollama-run-cold.txt"
COLD_LOAD="$(stat_of "$LOG_DIR/ollama-run-cold.txt" 'load duration')"
COLD_TOTAL="$(stat_of "$LOG_DIR/ollama-run-cold.txt" 'total duration')"
COLD_PROMPT_RATE="$(stat_of "$LOG_DIR/ollama-run-cold.txt" 'prompt eval rate')"
COLD_EVAL_RATE="$(stat_of "$LOG_DIR/ollama-run-cold.txt" 'eval rate')"
ok "load ${COLD_LOAD:-?} · total ${COLD_TOTAL:-?} · prompt eval ${COLD_PROMPT_RATE:-?} · eval ${COLD_EVAL_RATE:-?}"

echo "暖機後（較長的提示：範例專案的 Player.ts）"
ollama run "$LLM" --verbose "$LONG_PROMPT" > "$LOG_DIR/ollama-run-warm.txt" 2>&1 || fail "ollama run 失敗，見 $LOG_DIR/ollama-run-warm.txt"
WARM_PROMPT_COUNT="$(stat_of "$LOG_DIR/ollama-run-warm.txt" 'prompt eval count')"
WARM_PROMPT_RATE="$(stat_of "$LOG_DIR/ollama-run-warm.txt" 'prompt eval rate')"
WARM_EVAL_COUNT="$(stat_of "$LOG_DIR/ollama-run-warm.txt" 'eval count')"
WARM_EVAL_RATE="$(stat_of "$LOG_DIR/ollama-run-warm.txt" 'eval rate')"
ok "prompt eval ${WARM_PROMPT_RATE:-?}（${WARM_PROMPT_COUNT:-?}）· eval ${WARM_EVAL_RATE:-?}（${WARM_EVAL_COUNT:-?}）"
[ -n "$WARM_EVAL_RATE" ] || warn "沒有讀到 eval rate；ollama run --verbose 的輸出格式可能改了，見 $LOG_DIR/ollama-run-warm.txt"

# "SIZE" and "PROCESSOR" of one model in `ollama ps`.
ps_size() { grep -E "^$2[[:space:]]" "$1" | grep -oE '[0-9.]+ [KMGT]B' | head -n1 || true; }
ps_proc() { grep -E "^$2[[:space:]]" "$1" | grep -oE '[0-9]+%/[0-9]+% CPU/GPU|[0-9]+% (GPU|CPU)' | head -n1 || true; }
ollama ps > "$LOG_DIR/ollama-ps-run.txt" 2>&1 || true
cat "$LOG_DIR/ollama-ps-run.txt"
RUN_MEM="$(ps_size "$LOG_DIR/ollama-ps-run.txt" "$LLM")"
RUN_PROC="$(ps_proc "$LOG_DIR/ollama-ps-run.txt" "$LLM")"
case "$RUN_PROC" in
  "100% GPU") ok "$LLM 100% 在 GPU（Metal）上執行，記憶體 $RUN_MEM（ollama run 的預設上下文）" ;;
  *CPU/GPU*) warn "$LLM 只有部分在 GPU（$RUN_PROC）：記憶體不足，數據會偏慢。關閉其他程式後重跑，或記錄這個狀態" ;;
  "") warn "ollama ps 沒有列出 $LLM，無法確認 GPU" ;;
  *) fail "$LLM 在 $RUN_PROC 上執行，沒有使用 Metal。請確認 Ollama 是 macOS 版（不是 Docker 或 Rosetta 版）" ;;
esac
METAL_LOG=""
if [ -f "$HOME/.ollama/logs/server.log" ]; then
  METAL_LOG="$(grep -iE 'metal' "$HOME/.ollama/logs/server.log" | tail -n 3 | cut -c1-200 || true)"
  [ -n "$METAL_LOG" ] && ok "server.log 有 Metal 紀錄" && echo "${DIM}$METAL_LOG${RESET}"
fi

# ── 4. Stack and indexing ─────────────────────────────────────────────────
# Exports the settings of one group into the current (sub)shell. Everything the
# experiment plan varies is set explicitly, so .env cannot leak a switch in.
group_env() {
  export LLM_MODEL="$LLM" TOP_K="$BENCH_TOP_K" HYBRID_SEARCH=false SPLIT_RETRIEVAL=false DOC_TOP_K=1 \
    CHUNK_METADATA=false PROMPT_VARIANT=v1 SCORE_THRESHOLD='' RERANK=false
  [ "$WITH_RERANK" = 1 ] && export INSTALL_RERANK=true
  case "$1" in
    baseline) ;;
    hybrid-split) export HYBRID_SEARCH=true SPLIT_RETRIEVAL=true DOC_TOP_K=1 ;;
    hybrid-split-rerank)
      export HYBRID_SEARCH=true SPLIT_RETRIEVAL=true DOC_TOP_K=1 RERANK=true \
        RERANK_CANDIDATES="$RERANK_CANDIDATES_BENCH" RERANK_TOP_N="$BENCH_TOP_K" ;;
    *) echo "unknown group $1" >&2; return 1 ;;
  esac
}
group_switches() {
  case "$1" in
    baseline) echo "all off" ;;
    hybrid-split) echo "HYBRID_SEARCH=true SPLIT_RETRIEVAL=true DOC_TOP_K=1" ;;
    hybrid-split-rerank) echo "HYBRID_SEARCH=true SPLIT_RETRIEVAL=true DOC_TOP_K=1 RERANK=true RERANK_CANDIDATES=$RERANK_CANDIDATES_BENCH RERANK_TOP_N=$BENCH_TOP_K" ;;
  esac
}

# Waits for /health and checks it reports exactly the group's settings.
check_health() {
  group="$1"
  for _ in $(seq 1 90); do
    curl -fsS --max-time 5 "$HEALTH_URL" > "$LOG_DIR/health-$group.json" 2>/dev/null && break
    sleep 2
  done
  "$PY" - "$LOG_DIR/health-$group.json" "$group" "$LLM" "$BENCH_TOP_K" "$RERANK_CANDIDATES_BENCH" <<'PY'
import json, sys
path, group, llm, top_k, cands = sys.argv[1:6]
try:
    h = json.load(open(path))
except Exception as exc:
    sys.exit(f"/health did not answer: {exc}")
r = h.get("retrieval") or {}
want = {
    "status": ("ok", h.get("status")),
    "llm_model": (llm, (h.get("ollama") or {}).get("llm_model")),
    "top_k": (int(top_k), h.get("top_k")),
    "hybrid_search": (group != "baseline", r.get("hybrid_search")),
    "split_retrieval": (group != "baseline", r.get("split_retrieval")),
    "chunk_metadata": (False, r.get("chunk_metadata")),
    "prompt_variant": ("v1", r.get("prompt_variant")),
    "score_threshold": (None, r.get("score_threshold")),
    "rerank": (group.endswith("rerank"), r.get("rerank")),
    "reindex_needed": (False, bool((h.get("qdrant") or {}).get("reindex_needed"))),
}
if group != "baseline":
    want["doc_top_k"] = (1, r.get("doc_top_k"))
if group.endswith("rerank"):
    want["rerank_candidates"] = (int(cands), r.get("rerank_candidates"))
    want["rerank_top_n"] = (int(top_k), r.get("rerank_top_n"))
    want["reranker.installed"] = (True, (h.get("reranker") or {}).get("installed"))
bad = [f"{k}: want {w!r}, got {g!r}" for k, (w, g) in want.items() if w != g]
if bad:
    print("/health does not match the group settings:")
    print("\n".join("  " + b for b in bad))
    if any(b.startswith("reranker.installed") for b in bad):
        print("  → build the image with rerank: INSTALL_RERANK=true docker compose build backend")
    sys.exit(1)
print(f"/health ok: {llm}, top_k={top_k}, {group}")
PY
}

step "4. 啟動服務並計時索引"
if [ "$WITH_RERANK" = 1 ]; then
  echo "build backend 與 frontend（INSTALL_RERANK=true）"
else
  echo "build backend 與 frontend"
fi
( group_env baseline; docker compose build backend frontend )
STACK_TOUCHED=1
( group_env baseline; docker compose up -d --wait )
check_health baseline > /dev/null 2>&1 || true   # waits for the backend; indexing may still be needed
if [ "$WITH_RERANK" = 1 ]; then
  # Fail now rather than after the other groups: is the rerank code in the image?
  docker compose exec -T backend python -c \
    "import sys; from app.rerank import rerank_installed; sys.exit(0 if rerank_installed() else 1)" >/dev/null 2>&1 \
    || fail "backend 映像檔沒有 rerank 套件。請執行 INSTALL_RERANK=true docker compose build backend 後重跑"
  ok "backend 映像檔含 rerank 套件（INSTALL_RERANK=true）"
fi

# "Done in 12.3s — scanned 20, added …, chunks written 67" → fields
index_field() { grep -E '^Done in' "$1" | tail -n1 | sed -nE "s/.*$2 ([0-9.]+).*/\\1/p" || true; }
run_index() {
  name="$1"; shift
  t0="$(now)"
  set +e
  ( group_env baseline; ./scripts/index.sh "$@" ) > "$LOG_DIR/index-$name.log" 2>&1
  rc=$?
  set -e
  wall="$(since "$t0")"
  tail -n 3 "$LOG_DIR/index-$name.log" >&2
  [ "$rc" = 0 ] || fail "索引失敗（exit $rc），見 $LOG_DIR/index-$name.log"
  echo "$wall"   # the only line on stdout: wall-clock seconds
}
echo "全量索引（./scripts/index.sh --full）"
FULL_WALL="$(run_index full --full)"
FULL_SECONDS="$(index_field "$LOG_DIR/index-full.log" 'Done in')"
FILES_SCANNED="$(index_field "$LOG_DIR/index-full.log" scanned)"
FILES_SKIPPED="$(index_field "$LOG_DIR/index-full.log" skipped)"
CHUNKS_WRITTEN="$(index_field "$LOG_DIR/index-full.log" 'chunks written')"
ok "全量：索引器 ${FULL_SECONDS}s（含 compose 檢查的牆鐘時間 ${FULL_WALL}s），掃描 $FILES_SCANNED 個檔案、$CHUNKS_WRITTEN 個片段"

echo "增量索引，沒有變更（./scripts/index.sh）"
INCR_WALL="$(run_index incremental)"
INCR_SECONDS="$(index_field "$LOG_DIR/index-incremental.log" 'Done in')"
ok "增量：索引器 ${INCR_SECONDS}s（牆鐘 ${INCR_WALL}s）"

# ── 5. Evaluation groups ──────────────────────────────────────────────────
step "5. 檢索實驗（TOP_K=$BENCH_TOP_K；組別：$BENCH_GROUP_LIST）"
ONLY_MAIN=""; ONLY_IDENT=""
if [ "$QUICK" = 1 ]; then
  ONLY_MAIN="--only $QUICK_MAIN"; ONLY_IDENT="--only $QUICK_IDENT"
  warn "--quick：主要題組只跑 $QUICK_MAIN、識別字題組只跑 $QUICK_IDENT，結果寫到 $OUT_DIR（不進 docs/）"
fi
EVAL_FAILED=0
FIRST_GROUP=1
evaluate() {
  label="$1"; log="$2"; shift 2
  # Unload first: the next run starts without Ollama's cached prompt from the previous
  # group (devlog 2026-11-03, Problem 1); evaluate.py's warm-up query reloads the model.
  unload "$LLM"; unload "$EMBED_MODEL"; sleep 2
  set +e
  # shellcheck disable=SC2086
  "$PY" scripts/evaluate.py --base-url "$BASE_URL" --label "$label" --out-dir "$OUT_DIR" "$@" 2>&1 | tee "$log"
  rc=${PIPESTATUS[0]}
  set -e
  if [ "$rc" != 0 ]; then
    warn "$label：evaluate.py exit $rc（有題目失敗或服務沒有回應），見 $log"
    EVAL_FAILED=$((EVAL_FAILED + 1))
  fi
}
for group in $BENCH_GROUP_LIST; do
  echo
  echo "${BOLD}── $PREFIX-$group：$(group_switches "$group")${RESET}"
  ( group_env "$group"; docker compose up -d --wait backend ) >/dev/null
  ( group_env "$group"; check_health "$group" ) || fail "/health 與 $group 的設定不符，見上方"
  # shellcheck disable=SC2086
  evaluate "$PREFIX-$group" "$LOG_DIR/eval-$group.log" $ONLY_MAIN
  if [ "$FIRST_GROUP" = 1 ]; then
    ollama ps > "$LOG_DIR/ollama-ps-eval.txt" 2>&1 || true
    memory_pressure 2>/dev/null | grep -i 'free percentage' > "$LOG_DIR/memory-pressure.txt" || true
    FIRST_GROUP=0
  fi
  # shellcheck disable=SC2086
  evaluate "$PREFIX-$group-ident" "$LOG_DIR/eval-$group-ident.log" --questions docs/evaluation/questions-identifiers.yaml $ONLY_IDENT
done
echo
cat "$LOG_DIR/ollama-ps-eval.txt" 2>/dev/null || true
EVAL_MEM="$(ps_size "$LOG_DIR/ollama-ps-eval.txt" "$LLM")"
EVAL_PROC="$(ps_proc "$LOG_DIR/ollama-ps-eval.txt" "$LLM")"
MEM_FREE="$(sed -E 's/.*: *//' "$LOG_DIR/memory-pressure.txt" 2>/dev/null || true)"
ok "評估時（LLM_NUM_CTX=$LLM_NUM_CTX）：$LLM 記憶體 ${EVAL_MEM:-?}、${EVAL_PROC:-?}；系統可用記憶體 ${MEM_FREE:-?}"

# ── 6. Comparisons and summary ────────────────────────────────────────────
step "6. 比較與摘要"
DATE="$(date +%F)"
report() { echo "$OUT_DIR/$DATE-$PREFIX-$1.json"; }
compare() {
  a="$1"; b="$2"; out="$OUT_DIR/$DATE-$PREFIX-$a-vs-$b"
  for suffix in "" "-ident"; do
    if [ -f "$(report "$a$suffix")" ] && [ -f "$(report "$b$suffix")" ]; then
      if "$PY" scripts/compare.py "$(report "$a$suffix")" "$(report "$b$suffix")" --out "$out$suffix.md" > /dev/null; then
        ok "$out$suffix.md"
      else
        warn "compare.py 失敗：$a$suffix → $b$suffix"
      fi
    fi
  done
}
compare baseline hybrid-split
[ "$WITH_RERANK" = 1 ] && compare hybrid-split hybrid-split-rerank

SUMMARY="$OUT_DIR/$DATE-$PREFIX-summary.md"
# Total seconds of evaluate.py's warm-up query in the first group (printed on the line after "warm-up:").
FIRST_QUERY="$(grep -A1 '^warm-up:' "$LOG_DIR/eval-baseline.log" 2>/dev/null | tail -n1 | grep -oE '[0-9.]+s$' | tr -d s || true)"
export BENCH_DATE="$DATE" BENCH_PREFIX="$PREFIX" BENCH_OUT_DIR="$OUT_DIR" BENCH_GROUPS="$BENCH_GROUP_LIST" BENCH_QUICK="$QUICK" \
  BENCH_CHIP="$CHIP" BENCH_MEM_GB="$MEM_GB" BENCH_MACOS="$MACOS" BENCH_OLLAMA="$OLLAMA_VERSION" \
  BENCH_LLM="$LLM" BENCH_EMBED="$EMBED_MODEL" BENCH_TOP_K="$BENCH_TOP_K" BENCH_NUM_CTX="$LLM_NUM_CTX" \
  BENCH_RERANK_CANDIDATES="$RERANK_CANDIDATES_BENCH" BENCH_LLM_DOWNLOAD="$LLM_DOWNLOAD" \
  BENCH_COLD_LOAD="$COLD_LOAD" BENCH_COLD_TOTAL="$COLD_TOTAL" BENCH_COLD_PROMPT_RATE="$COLD_PROMPT_RATE" BENCH_COLD_EVAL_RATE="$COLD_EVAL_RATE" \
  BENCH_WARM_PROMPT_RATE="$WARM_PROMPT_RATE" BENCH_WARM_PROMPT_COUNT="$WARM_PROMPT_COUNT" \
  BENCH_WARM_EVAL_RATE="$WARM_EVAL_RATE" BENCH_WARM_EVAL_COUNT="$WARM_EVAL_COUNT" \
  BENCH_RUN_MEM="$RUN_MEM" BENCH_RUN_PROC="$RUN_PROC" BENCH_EVAL_MEM="$EVAL_MEM" BENCH_EVAL_PROC="$EVAL_PROC" BENCH_MEM_FREE="$MEM_FREE" \
  BENCH_FULL_SECONDS="$FULL_SECONDS" BENCH_FULL_WALL="$FULL_WALL" BENCH_INCR_SECONDS="$INCR_SECONDS" BENCH_INCR_WALL="$INCR_WALL" \
  BENCH_FILES="$FILES_SCANNED" BENCH_SKIPPED="$FILES_SKIPPED" BENCH_CHUNKS="$CHUNKS_WRITTEN" \
  BENCH_FIRST_QUERY="$FIRST_QUERY" \
  BENCH_LOG_DIR="$LOG_DIR"
"$PY" -I scripts/benchmark_summary.py > "$SUMMARY"
ok "摘要：$SUMMARY"

# ── 7. Back to .env ───────────────────────────────────────────────────────
step "7. 恢復 backend 為 .env 的設定"
restore_backend
ok "完成"

echo
echo "${BOLD}下一步${RESET}"
echo "  1. 打開 $SUMMARY，把表格貼到 docs/metrics.md 對應的段落（英文表格貼英文段、中文表格貼中文段）"
echo "  2. 讀過每份報告的回答，填寫「人工判定正確性」，再執行："
echo "       python3 scripts/evaluate.py --apply-manual <報告.md>"
echo "  3. 原始輸出（ollama run、ollama ps、索引、評估 log）：$LOG_DIR/"
[ "$EVAL_FAILED" = 0 ] || { warn "$EVAL_FAILED 次評估有錯誤，數據不完整"; exit 1; }
