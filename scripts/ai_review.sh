#!/bin/sh
# 用 headless DSH 会话对新评论做语义复核（分类 + 画师抽取 + 别名去重）
# 没有新评论时直接跳过，不消耗额度。
set -e
cd /vol1/1000/Data/codes/files/bili-painter-report
PY=$(python3 -c "import json;print(json.load(open('store/local.json'))['python'])")
DSH=$(python3 -c "import json;print(json.load(open('store/local.json')).get('dsh','dsh'))" 2>/dev/null || echo dsh)

N=$("$PY" -c "import json;print(len(json.load(open('store/pending.json'))['comments']))" 2>/dev/null || echo 0)
if [ "$N" = "0" ]; then
  echo "[$(date '+%F %T')] 无待复核评论，跳过 AI 步骤" >> store/ai.log
  exit 0
fi

echo "[$(date '+%F %T')] 交给 AI 复核 $N 条新评论" >> store/ai.log
"$DSH" --profile headless "请读取并严格执行 scripts/ai_prompt.md 里的任务；工作目录就是当前目录。" >> store/ai.log 2>&1
echo "[$(date '+%F %T')] AI 复核结束" >> store/ai.log
# 复核完清空队列，避免重复处理
"$PY" -c "import json;p='store/pending.json';d=json.load(open(p));d['comments']=[];d['count']=0;json.dump(d,open(p,'w'),ensure_ascii=False)"
