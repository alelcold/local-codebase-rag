#!/usr/bin/env bash
# 在 backend 容器內執行索引器，並即時顯示進度。
#
#   ./scripts/index.sh          # 增量索引：只處理新增/修改/刪除的檔案
#   ./scripts/index.sh --full   # 清空後完整重建
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ -t 0 ] && [ -t 1 ]; then
  exec docker compose exec backend python -m app.indexer "$@"
else
  exec docker compose exec -T backend python -m app.indexer "$@"
fi
