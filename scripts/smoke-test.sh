#!/usr/bin/env bash
# 端到端冒煙測試：對「已經啟動」的服務做健康檢查 → 索引 → 查詢 → 串流查詢，確認回應附有檔案引用。
# End-to-end smoke test against a running stack: health → index → query → streaming query → citations.
#
# 用法 / Usage:
#   ./scripts/smoke-test.sh
#   FRONTEND_URL=http://localhost:8080 BACKEND_URL=http://localhost:8000 ./scripts/smoke-test.sh
#
# 索引直接呼叫後端；查詢與串流查詢走前端的 /api（順便驗證 nginx 代理與關閉緩衝）。
# Indexing calls the backend directly; both queries go through the frontend's /api
# proxy so the nginx config (including unbuffered streaming) is exercised too.
# Set SKIP_STREAM=1 to skip the streaming query, STREAM_STRICT=1 to fail (not just
# warn) when the stream looks buffered (CI sets it). Needs curl and jq.
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

# ── Streaming query (/query/stream, Server-Sent Events; ADR 0010) ──────────────
if [ "${SKIP_STREAM:-0}" != "1" ]; then
  log "Streaming query through ${FRONTEND_URL}/api/query/stream"
  stream_file="$(mktemp)"; headers_file="$(mktemp)"
  trap 'rm -f "$stream_file" "$headers_file"' EXIT
  # -N: no curl buffering. --compressed: ask for gzip like a browser does, so a
  # proxy that compresses (and therefore buffers) the stream is caught too.
  # Each line is stamped with its arrival time (EPOCHREALTIME, bash 5+; empty
  # on older bash, which skips the timing check).
  curl -sS -N --compressed --fail-with-body --max-time "$QUERY_MAX_TIME" -X POST "${FRONTEND_URL}/api/query/stream" \
    -H 'Content-Type: application/json' -H 'Accept: text/event-stream' -D "$headers_file" \
    -d "$(jq -n --arg q "$QUESTION" '{question: $q}')" \
    | while IFS= read -r line; do printf '%s\t%s\n' "${EPOCHREALTIME:-}" "$line"; done > "$stream_file" \
    || { cut -f2- "$stream_file"; fail "streaming query request failed"; }
  content_type="$(tr -d '\r' < "$headers_file" | awk -F': ' 'tolower($1) == "content-type" { print $2 }' | tail -n1)"
  echo "Content-Type: ${content_type}"
  case "$content_type" in
    text/event-stream*) ;;
    *) cut -f2- "$stream_file"; fail "expected Content-Type text/event-stream, got '${content_type}'" ;;
  esac

  # Input lines are "arrival<TAB>raw SSE line"; output is "event<TAB>data<TAB>arrival".
  events="$(awk -F'\t' '{ line = substr($0, length($1) + 2) }
    line ~ /^event: / { ev = substr(line, 8) }
    line ~ /^data: /  { print ev "\t" substr(line, 7) "\t" $1 }' "$stream_file")"
  names="$(cut -f1 <<<"$events" | grep -v '^heartbeat$' | uniq | tr '\n' ' ')"
  echo "Events (heartbeats omitted, repeats collapsed): ${names}"

  if grep -q '^error'$'\t' <<<"$events"; then
    grep '^error'$'\t' <<<"$events" | cut -f2 | jq .
    fail "the stream reported an error event"
  fi
  [ "$(cut -f1 <<<"$events" | grep -v '^heartbeat$' | head -n1)" = "sources" ] || fail "the first event (after heartbeats) is not 'sources'"
  [ "$(cut -f1 <<<"$events" | tail -n1)" = "done" ] || fail "the stream did not end with 'done'"
  sources_json="$(grep '^sources'$'\t' <<<"$events" | head -n1 | cut -f2)"
  [ "$(jq 'length' <<<"$sources_json")" -gt 0 ] || fail "the sources event is empty"
  jq -e 'all(.[]; (.file_path | test("\\.(ts|tsx|js|jsx|mjs|cjs|md)$")) and .start_line >= 1 and .end_line >= .start_line)' \
    <<<"$sources_json" >/dev/null || fail "a streamed source is missing a file path or a valid line range"
  token_count="$(grep -c '^token'$'\t' <<<"$events" || true)"
  [ "$token_count" -gt 0 ] || fail "no token events"
  streamed_answer="$(grep '^token'$'\t' <<<"$events" | cut -f2 | jq -j .text)"
  [ -n "$streamed_answer" ] || fail "the streamed answer is empty"
  echo "--- streamed answer (${token_count} token events) ---"
  echo "$streamed_answer"
  echo "--- done ---"
  grep '^done'$'\t' <<<"$events" | cut -f2 | jq -c .

  # Soft check: if a proxy buffered the stream, every event would arrive at the
  # same moment at the end. Compare the client-side spread of arrival times with
  # how long the backend says the stream took.
  first_at="$(head -n1 <<<"$events" | cut -f3)"
  done_at="$(grep '^done'$'\t' <<<"$events" | cut -f3)"
  server_total="$(grep '^done'$'\t' <<<"$events" | cut -f2 | jq -r .total_seconds)"
  if [ -n "$first_at" ] && [ -n "$done_at" ]; then
    spread="$(awk -v a="$first_at" -v b="$done_at" 'BEGIN { printf "%.2f", b - a }')"
    if awk -v s="$spread" -v t="$server_total" 'BEGIN { exit !(t > 1 && s < 0.1) }'; then
      msg="All events arrived within ${spread}s although the backend streamed for ${server_total}s. Something between curl and the backend is buffering or compressing the stream (check proxy_buffering and gzip in frontend/nginx.conf.template)."
      [ "${STREAM_STRICT:-0}" = "1" ] && fail "$msg"
      echo "::warning::$msg"
    else
      log "Stream was delivered incrementally: events spread over ${spread}s (backend: ${server_total}s)"
    fi
  fi
fi

log "Smoke test passed"
