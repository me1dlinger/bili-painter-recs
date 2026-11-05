# B站评论区画师推荐分析 —— 任务说明书 / 重启手册

> **这个文件是干什么的**：本项目（抓取 B 站视频评论区画师推荐 → 生成网页 → 发布 GitHub Pages）
> 跑完或想暂停后，**照这个文件复制粘贴就能原地重启**。重启所需的一切（命令、提示词、
> 环境依赖、注意事项）都在下面，不需要看别的地方。

---

## 0. 一句话说明

盯住 B 站视频 **BV15cxq6tEFW**（《[视频标题见网页]》）的评论区，把里面被推荐/被点名的
**画师**抽出来做成榜单网页，每小时增量抓取一次，AI 只做语义判断（分类、归并、找新画师），
文件操作全部交给确定性脚本。

- **仓库/工作目录**：`/vol1/1000/Data/codes/files/bili-painter-report`
- **线上网页**：https://me1dlinger.github.io/bili-painter-recs/ （Pages 源目录 = `docs/`）
- **评论数上限**：**1000 条**（抓满即冻结，见第 5 节）

---

## 1. 两个定时任务（重启时要恢复的就是这两个）

### 任务 A：每小时抓取 → 构建 → 发布（系统 crontab）

```cron
0 * * * * /bin/sh /vol1/1000/Data/codes/files/bili-painter-report/scripts/cron_update.sh
```

**恢复方法**（在 NAS 上执行）：

```sh
crontab -l > /tmp/cron.bak 2>/dev/null   # 先备份现有 cron
cat >> /tmp/cron.new <<'EOF'
0 * * * * /bin/sh /vol1/1000/Data/codes/files/bili-painter-report/scripts/cron_update.sh
EOF
crontab /tmp/cron.new                      # 或手工把这些行合并进 crontab -e
crontab -l                                 # 确认写入
```

`cron_update.sh` 内部依次做 4 件事（无需人工介入）：

1. `python scripts/fetch.py --quiet` —— 增量抓评论（rpid 去重，楼中楼全翻，签到 pending 待复核）
2. `sh scripts/ai_review.sh` —— 只做「有新评论待复核」的标记，**不阻塞**（真正的复核由任务 B 完成）
3. `python scripts/build.py` —— 重建 `data.json` / `artists_raw.json` / `画师推荐榜.md` / `.csv`
4. `sh scripts/publish.sh` —— 拷进 `docs/` 并 `git push`（**带 3 次自动重试**，网络抖动不会断更）
5. 收尾：评论满 1000 且复核队列为空 → 写 `store/FROZEN`，后续轮次自动跳过（见第 5 节）

### 任务 B：AI 结构化复核（会话内定时提醒）

**这个不能由 crontab 完成**（需要模型做语义判断），它是一条会话定时提醒。
重启时，把下面这段**原样**作为提醒的 prompt 建一条 cron 提醒，时区 `Asia/Shanghai`，
表达式 `10 */4 * * *`（每 4 小时的第 10 分：00:10 / 04:10 / 08:10 / 12:10 / 16:10 / 20:10）。
错开第 10 分是为了等整点抓取跑完，保证能复核到最新评论。

```
到点了，检查 /vol1/1000/Data/codes/files/bili-painter-report/store/pending.json 的 count：为 0 就跳过（保持轻量）。有则走结构化复核流程：1) 跑 scripts/make_input.py 生成 store/review_input.json；2) 读它，按 scripts/ai_prompt.md 的固定 schema 填 store/review.json（只写这一个文件：分类 + mentions 里 name_as_written/canonical_guess/note，对照 knownArtists 归并，canonical_guess 沿用已有规范名，确认新画师才用新名）；3) 跑 scripts/merge_review.py（程序化删占位/追加提及/别名回写/清 pending/跑 build）；4) 跑 scripts/publish.sh 发布到 GitHub Pages。不要手改 mentions.json / config.json / artists_raw.json。
```

**恢复方法**：在会话里用定时提醒工具新建一条 cron 提醒，表达式 `10 */4 * * *`、时区
`Asia/Shanghai`、prompt 填上面那段原文、标题写「B站画师评论复核（每 4 小时 · 第 10 分）」。

---

## 2. AI 复核的固定契约（改脚本前必读）

设计原则：**AI 只出语义判断，文件操作全交给脚本**。这样不会因为模型发挥而写坏数据。

| 环节 | 脚本 | 作用 |
|---|---|---|
| 准备入参 | `scripts/make_input.py` | 生成 `store/review_input.json`（固定 schema：instructions / knownArtists / alias / notArtist / pending / count） |
| **AI 只填这个** | — | `store/review.json`（固定 schema：每条评论的 `category` / `artists` / `works` / `reason` / `mentions[]`） |
| 程序化合并 | `scripts/merge_review.py` | 删「自动匹配·待复核」占位 → 按 mentions 追加真实条目（key 去重 + 规范名查重）→ 别名回写 `config.alias` → 清已复核的 pending（**未复核的保留，防丢队列**）→ 跑 build |

分类口径（`category`）：`artist_rec` 点名画师 / `work_only` 只报作品未点名画师 / `ask` 求推荐求车牌 /
`chat` 闲聊 / `empty` 无实质内容。

**禁止手改**：`store/mentions.json`、`store/config.json`、`artists_raw.json`、`store/comments.json`。
要改数据只能通过复核流程（`review.json` → `merge_review.py`）。

---

## 3. 目录速查

```
bili-painter-report/
├── scripts/
│   ├── fetch.py            # 抓评论（凭证、上限 CAP=1000、自动匹配、pending 追加合并）
│   ├── ai_review.sh        # 复核标记（不阻塞）
│   ├── ai_prompt.md        # 给 AI 的 schema 说明（复核时读）
│   ├── make_input.py       # 生成复核入参
│   ├── merge_review.py     # 程序化合并复核结果（AI 不碰数据文件）
│   ├── build.py            # 重建 data.json / md / csv（含点赞统计、增量弹窗数据）
│   ├── publish.sh          # 拷 docs/ + git push（3 次重试）
│   └── cron_update.sh      # 每小时主链（含防并发锁、冻结收尾）
├── store/
│   ├── comments.json       # 评论库（rpid → 评论，按 ctime 排序，只增不减）
│   ├── mentions.json       # 提及表（画师 × 评论）
│   ├── pending.json        # 待 AI 复核队列
│   ├── config.json         # 人工配置：alias 别名表 / 精选作品表 / workOnly / 黑名单
│   ├── state.json          # 运行状态 + 上次发布快照（算增量用）
│   ├── review_input.json   # 复核入参（AI 读）
│   ├── review.json         # 复核结论（AI 写，每轮整体重写）
│   ├── FROZEN              # 【冻结标记】存在则抓取任务直接跳过
│   ├── update.lock         # 防并发锁
│   └── local.json          # 本机私有配置（不进仓库）：python 路径 / dutyHome / nodeBinDir
├── web/public/index.html   # 前端（改完要 publish 才生效）
├── docs/                   # GitHub Pages 源目录（由 publish.sh 同步，别手改）
├── data.json               # 前端数据（build 产物）
└── TASK.md                 # ← 本文件
```

---

## 4. 环境依赖（重启前确认）

1. **Python 环境**：`store/local.json` 里的 `python` 指向刷B站插件的独立 venv
   （`/vol1/@apphome/fn-deepseek-harness/bili-duty/.venv/bin/python`），里面装了 `bilibili_api`。
   若 venv 没了：用 MCP 的 `bili_setup` 重装，或按 `store/local.json` 的 `dutyHome` 重建。
2. **B站登录凭证**：`<dutyHome>/bili_credential.json`（4 个字段）。
   验证：插件工具 `bili_whoami`（当前账号：假面骑士鲸骑）。
   **凭证过期就抓不到评论**，需要用 `bili_login_start` + `bili_login_poll` 重新扫码。
3. **git 凭据 / 代理**：配置在 `/vol1/@appshare/fn-deepseek-harness/.gitconfig` 与 `.git-credentials`。
   `cron_update.sh` 里已显式 `export HOME=/vol1/@appshare/fn-deepseek-harness`——
   **cron 默认 HOME 是 `/home/fn-deepseek-harness`，读不到凭据会导致 push 失败**（踩过坑，别删这行）。
4. **GitHub 仓库**：`me1dlinger/bili-painter-recs`，Pages 源 = `main` 分支 `docs/` 目录。

---

## 5. 冻结机制（评论满 1000 条）

需求：网页「抓取评论 N 条」最终要**精确停在 1000**，不多不少；到数了就冻结网页、停止任务。

- **不多**：`fetch.py` 里 `CAP = 1000`。合并去重后若超过 1000，只保留按 `ctime` 升序的前 1000 条，
  多出来的新评论**直接不入库**（并从 `new_ids` / `pending` 里剔除，避免产生对不存在评论的提及）。
- **不少**：评论库是「只增不减」的合并策略（已存在的评论只更新点赞数/内容），所以数字会稳稳涨到 1000。
- **冻结条件**：`data.json` 的 `meta.totalCount >= 1000` **且** `store/pending.json` 的 `count == 0`
  （即最后一批评论也已经过 AI 复核，分类准确），此时 `cron_update.sh` 会写 `store/FROZEN`，
  之后每一轮都直接跳过（不再抓取、不再发布），网页停在最后一版快照。
- **收尾清理**（可选的最后一步）：确认 `store/FROZEN` 已生成后，可以移除定时任务本身，让机器彻底安静：

  ```sh
  # 1) 移除 crontab 任务（只删这一行，保留其它 cron）
  crontab -l | grep -v 'cron_update.sh' | crontab -
  crontab -l      # 确认已移除

  # 2) 会话侧的 AI 复核提醒：在会话里删掉那条「B站画师评论复核」cron 提醒
  ```

  > 脚本**不会**自己删 crontab（避免误删机器上其它任务），所以这一步由人确认后执行。
  > 不删也没关系：`store/FROZEN` 会让任务空转跳过，不会改动任何数据。

### 想解冻 / 继续跑

```sh
cd /vol1/1000/Data/codes/files/bili-painter-report
rm store/FROZEN                      # 解除冻结（注意：会继续抓，可能又超 1000 被裁）
crontab -l | grep cron_update        # 若无输出，按第 1 节重新加回 crontab
```

> 若想把上限改成别的数（比如 1200）：改 `scripts/fetch.py` 的 `CAP`，同时改
> `scripts/cron_update.sh` 里的 `CAP=1000` 和冻结判断，再重建会话提醒。

---

## 6. 手动跑一轮（不想等 crontab 时）

```sh
cd /vol1/1000/Data/codes/files/bili-painter-report
PY=/vol1/@apphome/fn-deepseek-harness/bili-duty/.venv/bin/python

$PY scripts/fetch.py --quiet     # 抓
sh scripts/ai_review.sh          # 标记待复核
$PY scripts/build.py             # 重建数据
sh scripts/publish.sh            # 发布（含重试）
```

只想看状态：

```sh
$PY -c "import json;p=json.load(open('store/pending.json'));print('待复核',p['count'])"
$PY -c "import json;d=json.load(open('data.json'));print(d['meta']['totalCount'],'条评论 /',d['stats']['artistCount'],'画师 /',d['stats']['mentionCount'],'提及')"
tail -20 store/update.log        # 看看最近几轮跑得怎么样
```

---

## 7. 踩过的坑（重启后别再踩）

1. **AI 复核与抓取并发会丢队列** → 已修：`fetch.py` 的 pending 是「追加合并」，`merge_review.py` 只清
   已复核的 rpid，未复核的一律保留。
2. **AI 手写画师名会拼错**（曾把 `momonosuke` 写成 `momonosunosuke`）→ 所以规范名一律从
   `knownArtists` 里抄，缺字段时走「旧格式兼容」分支，不让模型自由发挥。
3. **老格式 review（只有 artists 没有 mentions）会造成重复条目** → 已加规范名查重。
4. **cron 环境 push 失败**（读不到 git 凭据）→ `cron_update.sh` 里显式 `export HOME`。
5. **网络抖动导致 push 失败** → `publish.sh` 已加 3 次自动重试（实测救回多次 TLS 握手失败 / HTTP 408）。
6. **改前端后忘记 publish** → 网页上的 `index.html` 来自 `docs/`，必须跑 `publish.sh` 才生效。
7. **`docs/` 是产物目录**：不要手改，一切改动改 `web/public/index.html` 后再同步。

---

## 8. 冻结时的状态快照（自动更新，仅供对照）

见 `store/FROZEN`（冻结时生成，含冻结时间与当时的评论数）。
上线数据以 `data.json` 的 `meta` / `stats` 为准。