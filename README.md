> 内容提示：本仓库是 B 站公开评论区的画师提及统计，包含评论原文中的口语化描述；仓库与展示页均为公开。

# B站评论区画师推荐分析

把视频 [BV15cxq6tEFW](https://www.bilibili.com/video/BV15cxq6tEFW)（《牛哥力荐！瓶子爽聊最近的画师入驻b站…》）评论区的**全部画师/作者推荐**抽取、去重、结构化，并提供一个局域网可访问的分析网页。

## 看数据

**在线（GitHub Pages）：https://me1dlinger.github.io/bili-painter-recs/**

**局域网：**

```bash
cd web && node server.js 8787      # 启动后访问 http://<本机IP>:8787
```

- 网页：单页 master-detail，左侧画师密集列表（391 位，一屏约 21 行）+ 右侧详情面板；下方依次是作品表、评论分类、口径说明
- 一键复制：点画师名即复制该名字；`复制全部画师名` 输出一行一个的纯名字列表（受搜索/筛选影响）
- 支持深色模式、移动端（点列表行弹出底部抽屉）、键盘操作（`/` 搜索、`↑` `↓` 选择、`Enter` 复制名字）

## 文件

```
store/                数据仓（唯一真源）
  comments.json       评论原文，精简字段：rpid/user/content/like/rcount/ctime/isSub/root
  mentions.json       画师提及记录（LLM 抽取 + 自动匹配），按评论去重
  config.json         别名归一表、低置信名单、作品表、手写标注
  state.json          上次抓取状态（时间 / 新增数）
  update.log          定时任务日志
scripts/
  fetch.py            增量抓取：一级 + 全部楼中楼，按 rpid 去重合并
  make_input.py       生成 AI 复核的结构化入参（review_input.json）
  merge_review.py     程序化合并 AI 复核结果（删占位/追加提及/别名回写/清队列）
  build.py            重建 artists_raw.json / data.json / 画师推荐榜.md / .csv
  cron_update.sh      fetch + build + publish 的 cron 包装（复核由主会话定时做）
  ai_prompt.md        给 AI 复核的固定 schema 说明
  publish.sh          同步 docs/ 并推送 GitHub
web/
  server.js           零依赖静态服务 + /api/data
  public/index.html   单文件前端
data.json             网页读取的数据
画师推荐榜.md / .csv   结构化文档
```

## 自动更新（每小时）

由 crontab 驱动，一条链跑完并自动发布到 GitHub Pages：

```
fetch.py       增量抓取评论，按 rpid 去重；新评论写进 store/pending.json
make_input.py  生成结构化复核入参 store/review_input.json（pending + 已知画师名单 + 别名表）
merge_review.py 把 AI 填好的 store/review.json 程序化合并（删占位/追加提及/别名回写/清队列）
build.py       重建 data.json / 画师推荐榜.md / .csv
publish.sh     同步到 docs/ 并 git push → Pages 自动刷新
```

**AI 复核那一步做什么**（纯代码做不到的部分，AI 只填 `store/review.json` 的结构化字段，
文件合并全部由 `merge_review.py` 完成，杜绝手改 JSON 出错）：

- 语义分类：这条评论是「推荐画师 / 只报作品 / 提问 / 普通闲聊 / 无内容」
- 抽画师：包括**数据库里还没有的新画师名**（字符串匹配只能认已知的名字）
- 去重归并：判断新写法是否其实是已有画师的别名（简繁、中日、罗马音、大小写、昵称、错别字），是则沿用旧条目
- 入参出参均固定 schema：`make_input.py` 产出入参，AI 按 `scripts/ai_prompt.md` 填出参，
  `merge_review.py` 合并进 `store/mentions.json`（追加提及）与 `store/config.json`（别名回写），
  并清空 `store/pending.json`；`build.py` 优先采信 AI 结论

没有新评论时 AI 步骤自动跳过，不消耗额度。

```bash
crontab -l                          # 查看
crontab -e                          # 改时间
sh scripts/cron_update.sh           # 手动跑一整轮（含发布）
sh scripts/publish.sh               # 只重新发布当前数据
tail -f store/update.log store/ai.log
```

去重逻辑：以 `rpid` 为唯一键，已存在的评论只更新点赞数/回复数，不重复入库；新评论先按「已知画师名 + 别名」自动匹配，命中的写入 `mentions.json` 并标注「自动匹配 · 待复核」，agent 醒来时再人工复核。

## 分类口径

| 分类 | 含义 |
| --- | --- |
| 画师推荐 | 评论正文直接点名了画师（日文名 / 中文名 / 罗马音 / 昵称） |
| 推荐作品（未点名） | 只报作品名或配图描述；楼中楼补出画师名的，画师计入画师榜 |
| 求推荐 / 提问 | 求车牌、问作者名、求推荐 |
| 普通评论 | 感慨、玩梗、点评平台 |
| 无实质内容 | @某人、表情、单字、纯数字 |

计数：同一画师的多种写法合并为一条；「提及次数」= 评论里出现的次数，「推荐人数」= 提到该画师的不同用户数。橙色圆点标记的名字疑似社团名或简称，保留原样供核对。

## 数据来源

一级评论走**两条通道取并集**，二级评论走 `x/v2/reply/reply` 逐楼翻页：

| 通道 | 接口 | 特点 |
| --- | --- | --- |
| 懒加载 | `x/v2/reply/main` | 只返回「热门评论池」，**会整栋漏掉部分热楼** |
| 分页 | `x/v2/reply`（pn） | 能翻到懒加载漏掉的楼 |

> 2026-11-02 踩坑记录：只走懒加载时，一条 `rcount=296` 的「评论区的各位一人一个推荐画师」整栋缺失，
> 导致总数停在 537 而接口声明是 837。加上旧接口后，839/839 完整覆盖。
> 二级评论按声明条数翻到底，不设截断上限。

凭证放在本机（`store/login/`，已 gitignore），不进仓库。