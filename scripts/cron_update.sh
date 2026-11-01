#!/bin/sh
# 每 12 小时增量抓取评论并重建数据。由 crontab 调用，也可手动执行。
set -e
cd /vol1/1000/Data/codes/files/bili-painter-report
PY=/vol1/@apphome/fn-deepseek-harness/bili-duty/.venv/bin/python
{
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') 开始 ====="
  "$PY" scripts/fetch.py --quiet
  "$PY" scripts/build.py
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') 完成 ====="
} >> store/update.log 2>&1
