# B站评论区画师推荐分析

把视频 [BV15cxq6tEFW](https://www.bilibili.com/video/BV15cxq6tEFW)（《牛哥力荐！瓶子爽聊最近的画师入驻b站…》）评论区的**全部画师/作者推荐**抽取、去重、结构化，并提供一个局域网可访问的分析网页。

## 看数据

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
  build.py            重建 artists_raw.json / data.json / 画师推荐榜.md / .csv
  cron_update.sh      fetch + build 的 cron 包装
web/
  server.js           零依赖静态服务 + /api/data
  public/index.html   单文件前端
data.json             网页读取的数据
画师推荐榜.md / .csv   结构化文档
```

## 自动更新

每 12 小时（10:00 / 22:00，Asia/Shanghai）自动增量抓取一次：

- 会话内定时任务（DSH 调度器）：到点唤醒 agent，跑脚本并对新评论做一次画师识别
- 系统兜底：crontab `0 10,22 * * * /bin/sh …/scripts/cron_update.sh`，即使会话没开着也会更新

```bash
crontab -l                          # 查看
crontab -e                          # 改时间
sh scripts/cron_update.sh           # 手动跑一次
tail -f store/update.log            # 看日志
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

凭证取自 `dsh-bili-scroll` 插件内置的 bilibili-mcp 服务（`/vol1/@apphome/fn-deepseek-harness/bili-duty/bili_credential.json`）。
一级评论走 `x/v2/reply/main` 分页，二级评论走 `x/v2/reply/reply` 逐楼翻页。