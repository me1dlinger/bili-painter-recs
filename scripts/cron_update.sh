#!/bin/sh
# 每 12 小时：抓取 → AI 语义复核 → 重建 → 发布到 GitHub Pages
set -e
cd /vol1/1000/Data/codes/files/bili-painter-report
PY=$(python3 -c "import json;print(json.load(open('store/local.json'))['python'])")
{
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') 开始 ====="
  "$PY" scripts/fetch.py --quiet          # 1. 增量抓取（rpid 去重）
  sh scripts/ai_review.sh                 # 2. 新评论交给 AI 做语义判断
  "$PY" scripts/build.py                  # 3. 重建 data.json / md / csv
  sh scripts/publish.sh                   # 4. 推到 GitHub，Pages 自动刷新
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') 完成 ====="
} >> store/update.log 2>&1
