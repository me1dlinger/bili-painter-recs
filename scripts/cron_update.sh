#!/bin/sh
# 每小时（crontab: 0 * * * *）：抓取 → 构建 → 发布到 GitHub Pages
# （AI 语义复核由主会话的定时提醒完成：每小时第 10 分，见 scripts/ai_prompt.md + merge_review.py）
set -e
cd /vol1/1000/Data/codes/files/bili-painter-report
# cron 的 PATH 极简，补上 node / git 所在目录
NODEDIR=$(python3 -c "import json;print(json.load(open('store/local.json')).get('nodeBinDir',''))" 2>/dev/null || echo "")
[ -n "$NODEDIR" ] && PATH="$NODEDIR:/usr/local/bin:/usr/bin:/bin:$PATH" && export PATH
PY=$(python3 -c "import json;print(json.load(open('store/local.json'))['python'])")
# git 凭据与代理配置在 /vol1/@appshare/fn-deepseek-harness/.gitconfig 与 .git-credentials；
# cron 默认 HOME 是 passwd 里的 /home/fn-deepseek-harness，找不到凭据会导致 push 失败（实测 fatal: could not read Username）。
# 显式指过去，让 git 能读到凭据与代理。
export HOME=/vol1/@appshare/fn-deepseek-harness
{
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') 开始 ====="
  # 防并发：上一轮还没跑完就跳过本轮（fetch 全量抓可能耗时数分钟）
  LOCK=store/update.lock
  if [ -f "$LOCK" ] && kill -0 "$(cat "$LOCK")" 2>/dev/null; then
    echo "上一轮（pid $(cat "$LOCK")）仍在运行，跳过本轮"
    echo "===== $(date '+%Y-%m-%d %H:%M:%S') 跳过（并发） ====="
    exit 0
  fi
  echo $$ > "$LOCK"
  trap 'rm -f "$LOCK"' EXIT
  "$PY" scripts/fetch.py --quiet          # 1. 增量抓取（rpid 去重）
  sh scripts/ai_review.sh                 # 2. 新评论交给 AI 做语义判断（标记，不阻塞）
  "$PY" scripts/build.py                  # 3. 重建 data.json / md / csv
  sh scripts/publish.sh                   # 4. 推到 GitHub，Pages 自动刷新
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') 完成 ====="
} >> store/update.log 2>&1
