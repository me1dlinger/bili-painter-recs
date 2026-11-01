#!/bin/sh
# 把最新的网页与数据同步到 docs/ 并推送到 GitHub（Pages 源目录 = docs/）
set -e
cd /vol1/1000/Data/codes/files/bili-painter-report
cp web/public/index.html docs/index.html
cp data.json docs/data.json
git add -A
if git diff --cached --quiet; then
  echo "无变化，跳过提交"
  exit 0
fi
git commit -q -m "data: 更新评论区画师数据 $(date '+%Y-%m-%d %H:%M')"
git push -q origin main
echo "已推送：$(git rev-parse --short HEAD)"
