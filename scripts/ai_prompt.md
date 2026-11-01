# 任务：复核新评论的语义分类与画师抽取

工作目录：`/vol1/1000/Data/codes/files/bili-painter-report`

`store/pending.json` 里是刚抓到的新评论（字段：rpid / user / content / like / isSub / root / autoMatched）。
`autoMatched` 只是拿「已知画师名的字符串匹配」猜的，不可靠，必须你自己读语义判断。

## 请对每条评论做三件事

1. **分类**（category）：
   - `artist_rec` 正文点名了画师／作者（中文名、日文名、罗马音、昵称都算）
   - `work_only` 只报作品名或只配图描述，没点名画师
   - `ask` 求车牌、问作者名、求推荐
   - `chat` 感慨、玩梗、点评平台，未针对具体画师
   - `empty` @某人、表情、单字、纯数字
2. **抽画师**：把正文里出现的画师名逐个抽出来，连同作品名、风格/评价描述一起记下。
   只抽**真的出现在正文里**的名字，不要凭印象补，也不要因为配图就编名字。
3. **去重判断**（关键）：
   - 先比对 `artists_raw.json` 里已有的画师名与别名。如果新写法其实是同一位（简繁差异、中文/日文/罗马音、昵称、错别字），**沿用已有的规范名**，并把这个新写法记进 `aliases`，不要新建条目。
   - 确认是新画师才用新名字。

## 输出（写文件，不要只回复文字）

1. `store/mentions.json`：把新抽到的提及**追加**进 `mentions` 数组，每条字段——
   `root_no`（可留 0）、`commenter`、`is_sub`、`name_as_written`、`canonical_guess`、`context`（原文片段）、`note`（评价/作品）、`rpid`（必须填，用于精确定位）。
2. `store/review.json`：`{"generatedAt": "...", "comments": {"<rpid>": {"category": "...", "artists": ["..."], "works": ["..."], "reason": "一句话理由"}}}`
3. 跑 `python scripts/build.py` 重建 data.json 与文档（用 /vol1/@apphome/fn-deepseek-harness/bili-duty/.venv/bin/python）。

## 纪律

- **只处理 `store/pending.json` 里真实存在的评论**，不要写入任何示例/测试数据。
- **不要新建额外脚本文件**（例如 merge_pending.py），直接改 JSON 即可。
- `store/review.json` 每轮**整体重写**，不要累加上一轮的内容。

## 汇报

最后用 3-5 行说明：复核了几条、分类结果、抽到哪些画师、有没有归并到已有条目。不要贴长日志。
