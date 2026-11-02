#!/bin/sh
# 每小时：抓取 → 构建 → 发布到 GitHub Pages
# （AI 语义复核由主会话的定时提醒完成，见 scripts/ai_prompt.md + merge_review.py）
set -e
cd /vol1/1000/Data/codes/files/bili-painter-report
# cron 的 PATH 极简，补上 node / git 所在目录
NODEDIR=$(python3 -c "import json;print(json.load(open('store/local.json')).get('nodeBinDir',''))" 2>/dev/null || echo "")
[ -n "$NODEDIR" ] && PATH="$NODEDIR:/usr/local/bin:/usr/bin:/bin:$PATH" && export PATH
PY=$(python3 -c "import json;print(json.load(open('store/local.json'))['python'])")
{
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') 开始 ====="
  "$PY" scripts/fetch.py --quiet          # 1. 增量抓取（rpid 去重）
  sh scripts/ai_review.sh                 # 2. 新评论交给 AI 做语义判断
  "$PY" scripts/build.py                  # 3. 重建 data.json / md / csv
  sh scripts/publish.sh                   # 4. 推到 GitHub，Pages 自动刷新
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') 完成 ====="
} >> store/update.log 2>&1
