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
  # 冻结检查：评论数达上限并完整发布过之后，本项目停止更新（见 store/FROZEN、TASK.md）
  if [ -f store/FROZEN ]; then
    echo "已冻结（store/FROZEN 存在），跳过本轮；重启方法见 TASK.md"
    echo "===== $(date '+%Y-%m-%d %H:%M:%S') 跳过（已冻结） ====="
    exit 0
  fi
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
  # ---------- 5. 收尾：评论抓满 1000 且复核队列已清空 → 冻结项目 ----------
  # 冻结 = 写 store/FROZEN（后续轮次直接跳过）+ 移除本 crontab 任务。
  # 会话侧的定时复核提醒也会做同样的收尾（双保险）。
  CAP=1000
  TOTAL=$("$PY" -c "import json;print(json.load(open('data.json',encoding='utf-8'))['meta']['totalCount'])")
  PEND=$("$PY" -c "import json;print(json.load(open('store/pending.json',encoding='utf-8')).get('count',0))" 2>/dev/null || echo 0)
  if [ "$TOTAL" -ge "$CAP" ] && [ "$PEND" -eq 0 ]; then
    "$PY" - <<'PYEOF'
import json, datetime
total = json.load(open("data.json", encoding="utf-8"))["meta"]["totalCount"]
json.dump({
    "frozenAt": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "totalComments": total,
    "cap": 1000,
    "reason": "评论数已达上限且复核队列已清空，抓取/发布任务停止",
    "restart": "重启步骤见 TASK.md（重新加 crontab + 重建会话定时复核）",
}, open("store/FROZEN", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"已冻结：评论 {total} 条（上限 1000），复核队列为空")
PYEOF
    echo "已写冻结标记 store/FROZEN：后续轮次将直接跳过，网页停在当前快照。"
    echo "（crontab 任务与会话定时复核的移除，由人工/会话侧确认后执行，见 TASK.md）"
  fi
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') 完成 ====="
} >> store/update.log 2>&1
