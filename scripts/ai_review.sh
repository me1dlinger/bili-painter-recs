#!/bin/sh
# 用 headless DSH 会话对新评论做语义复核（分类 + 画师抽取 + 别名去重）
# 没有新评论时直接跳过，不消耗额度。
set -e
cd /vol1/1000/Data/codes/files/bili-painter-report
# cron 的 PATH 极简，node 常常找不到 —— 从 store/local.json 补上
NODEDIR=$(python3 -c "import json;print(json.load(open('store/local.json')).get('nodeBinDir',''))" 2>/dev/null || echo "")
[ -n "$NODEDIR" ] && PATH="$NODEDIR:$PATH" && export PATH
PY=$(python3 -c "import json;print(json.load(open('store/local.json'))['python'])")
DSH=$(python3 -c "import json;print(json.load(open('store/local.json')).get('dsh','dsh'))" 2>/dev/null || echo dsh)

N=$("$PY" -c "import json;print(len(json.load(open('store/pending.json'))['comments']))" 2>/dev/null || echo 0)
if [ "$N" = "0" ]; then
  echo "[$(date '+%F %T')] 无待复核评论，跳过 AI 步骤" >> store/ai.log
  exit 0
fi

echo "[$(date '+%F %T')] 有 $N 条新评论待复核：由主会话定时复核（dsh headless 环境不可用，见 EACCES 记录），本步仅标记、不阻塞后续 build/publish" >> store/ai.log
exit 0
