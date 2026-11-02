#!/usr/bin/env bash
# 在 backend 容器內執行索引器，並即時顯示進度。
#
#   ./scripts/index.sh          # 增量索引：只處理新增/修改/刪除的檔案
#   ./scripts/index.sh --full   # 清空後完整重建
#
# 設定變更時自動全量重建（ADR 0013）：
#   每個片段都記錄了建立索引時的設定（index_config：切塊器版本、embedding 內容格式、
#   CHUNK_MAX_CHARS、EMBED_MODEL、文件前綴、CHUNK_METADATA）。索引器發現目前設定與
#   索引中的不同時，會自己清空 collection 並全部重建，並印出新舊設定。
#
#   改了 .env 卻沒有重建容器時，容器裡還是舊的設定，索引器看不到改變。所以這裡先執行
#   `docker compose up -d backend`：設定沒變時什麼都不做，有變時用目前的 .env（以及 shell
#   中同名的環境變數）重建 backend 容器，再執行索引。
#   設定 INDEX_SKIP_COMPOSE_UP=1 可略過這一步。
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ "${INDEX_SKIP_COMPOSE_UP:-0}" != "1" ]; then
  docker compose up -d --wait backend >&2
fi

if [ -t 0 ] && [ -t 1 ]; then
  exec docker compose exec backend python -m app.indexer "$@"
else
  exec docker compose exec -T backend python -m app.indexer "$@"
fi
