#!/bin/sh
# 把最新的网页与数据同步到 docs/ 并推送到 GitHub（Pages 源目录 = docs/）
set -e
cd /vol1/1000/Data/codes/files/bili-painter-report
cp web/public/index.html docs/index.html
cp data.json docs/data.json

# 记下这次发布的快照，供下一轮 build 计算「相对上次发布」的增量
python3 - <<'PYEOF'
import json, datetime, os
d = json.load(open("data.json", encoding="utf-8"))
sp = "store/state.json"
st = json.load(open(sp, encoding="utf-8")) if os.path.exists(sp) else {}
st["published"] = {
    "at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "comments": d["meta"]["totalCount"],
    "artists": d["stats"]["artistCount"],
    "mentions": d["stats"]["mentionCount"],
    "artistNames": [a["name"] for a in d["artists"]],
    "workTitles": [w["title"] for w in d["works"]],
}
json.dump(st, open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("发布快照:", st["published"])
PYEOF
git add -A
if git diff --cached --quiet; then
  echo "无变化，跳过提交"
  exit 0
fi
git commit -q -m "data: 更新评论区画师数据 $(date '+%Y-%m-%d %H:%M')"
# git push 偶发网络失败（TLS 握手等），自动重试最多 3 次，避免整点轮断更
n=0
while ! git push -q origin main; do
  n=$((n+1))
  if [ "$n" -ge 3 ]; then
    echo "推送失败（已重试 3 次），请稍后手动执行 git push origin main"
    exit 1
  fi
  echo "推送失败，3 秒后重试（第 $n 次）"
  sleep 3
done
echo "已推送：$(git rev-parse --short HEAD)"
