#!/usr/bin/env bash
# 端到端冒煙測試：對「已經啟動」的服務做健康檢查 → 索引 → 查詢，確認回應附有檔案引用。
# End-to-end smoke test against a running stack: health → index → query → citations.
#
# 用法 / Usage:
#   ./scripts/smoke-test.sh
#   FRONTEND_URL=http://localhost:8080 BACKEND_URL=http://localhost:8000 ./scripts/smoke-test.sh
#
# 索引直接呼叫後端；查詢走前端的 /api（順便驗證 nginx 代理）。
# Indexing calls the backend directly; the query goes through the frontend's /api
# proxy so the nginx config is exercised too. Needs curl and jq.
set -euo pipefail

BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
FRONTEND_URL="${FRONTEND_URL:-http://localhost:8080}"
QUESTION="${SMOKE_QUESTION:-How is the score calculated and where is it displayed?}"
HEALTH_RETRIES="${HEALTH_RETRIES:-30}"
# 查詢上限要比 LLM_REQUEST_TIMEOUT 長，讓後端自己的逾時錯誤先出現。
QUERY_MAX_TIME="${QUERY_MAX_TIME:-600}"

log()  { echo "==> $*"; }
fail() { echo "✗ $*" >&2; exit 1; }

command -v jq >/dev/null || fail "jq is required"

log "Waiting for ${BACKEND_URL}/health to report status=ok"
health=""
for i in $(seq 1 "$HEALTH_RETRIES"); do
  # -sS: quiet, but still print curl errors (plain -s hides them).
  if health="$(curl -sS --max-time 10 "${BACKEND_URL}/health")" \
     && [ "$(jq -r .status <<<"$health")" = "ok" ]; then
    break
  fi
  [ "$i" = "$HEALTH_RETRIES" ] && { echo "$health" | jq . 2>/dev/null || echo "$health"; fail "backend never became healthy"; }
  sleep 2
done
jq '{status, ollama: {ok: .ollama.ok, llm_model: .ollama.llm_model, embed_model: .ollama.embed_model}, qdrant: {ok: .qdrant.ok}}' <<<"$health"

log "Indexing the mounted project (full, wait=true)"
index="$(curl -sS --fail-with-body --max-time 900 -X POST "${BACKEND_URL}/index" \
  -H 'Content-Type: application/json' -d '{"full": true, "wait": true}')" \
  || { echo "$index"; fail "indexing request failed"; }
jq '{state, report: {scanned: .report.scanned, chunks_written: .report.chunks_written, duration_seconds: .report.duration_seconds, errors: .report.errors}}' <<<"$index"
[ "$(jq -r .state <<<"$index")" = "done" ] || fail "indexing did not finish"
[ "$(jq -r '.report.chunks_written' <<<"$index")" -gt 0 ] || fail "indexing wrote no chunks"
[ "$(jq -r '.report.errors | length' <<<"$index")" = "0" ] || fail "indexing reported file errors"

log "Querying through ${FRONTEND_URL}/api/query: ${QUESTION}"
start=$(date +%s)
answer="$(curl -sS --fail-with-body --max-time "$QUERY_MAX_TIME" -X POST "${FRONTEND_URL}/api/query" \
  -H 'Content-Type: application/json' \
  -d "$(jq -n --arg q "$QUESTION" '{question: $q}')")" \
  || { echo "$answer"; fail "query request failed"; }
echo "Query took $(( $(date +%s) - start ))s"

echo "--- answer ---"
jq -r .answer <<<"$answer"
echo "--- sources ---"
jq -r '.sources[] | "[\(.ref)] \(.file_path):\(.start_line)-\(.end_line)"' <<<"$answer"

# Hard checks: the answer is non-empty and cites real files with valid line ranges.
[ -n "$(jq -r '.answer | select(length > 0)' <<<"$answer")" ] || fail "empty answer"
[ "$(jq '.sources | length' <<<"$answer")" -gt 0 ] || fail "no file citations in the response"
jq -e 'all(.sources[]; (.file_path | test("\\.(ts|tsx|js|jsx|mjs|cjs|md)$")) and .start_line >= 1 and .end_line >= .start_line)' \
  <<<"$answer" >/dev/null || fail "a source is missing a file path or a valid line range"

# Soft check: tiny CI models do not always follow the [n] citation format.
if jq -e '.answer | test("\\[[0-9]+\\]")' <<<"$answer" >/dev/null; then
  log "Answer text cites excerpts with [n]"
else
  echo "::warning::Answer text has no [n] citation (common with the smallest model); sources were still returned."
fi

log "Smoke test passed"
