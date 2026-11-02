# 任务：复核新评论（只填结构化字段，不做任何文件操作）

工作目录：`/vol1/1000/Data/codes/files/bili-painter-report`

**入参**：`store/review_input.json`（由 `scripts/make_input.py` 生成，字段固定）：
- `pending`：待复核评论（rpid / user / content / isSub / root / autoMatched）
- `knownArtists`：当前全部已知画师（规范名 + 别名），**归并判断的唯一依据**
- `alias`：已有别名映射表；`notArtist`：已知非画师词

**出参**：只写 `store/review.json` 一个文件，schema 固定如下（整体重写，不要累加）：

```json
{
  "generatedAt": "2026-11-02 22:00:00",
  "comments": {
    "<rpid>": {
      "category": "artist_rec | work_only | ask | chat | empty",
      "artists": ["规范名1", "规范名2"],
      "works": ["作品名"],
      "reason": "一句话理由",
      "mentions": [
        {"name_as_written": "正文里的写法", "canonical_guess": "归并后的规范名", "note": "评价/作品（可空）"}
      ]
    }
  }
}
```

## 对每条评论做三件事（这是你唯一的职责，纯语义判断）

1. **分类**（category）：
   - `artist_rec` 正文点名了画师／作者（中文名、日文名、罗马音、昵称都算）
   - `work_only` 只报作品名或只配图描述，没点名画师
   - `ask` 求车牌、问作者名、求推荐
   - `chat` 感慨、玩梗、点评平台，未针对具体画师
   - `empty` @某人、表情、单字、纯数字
2. **抽画师**（写进 `mentions`）：只抽**正文里真实出现**的名字，一个名字一条记录；不要凭印象补，不要因为配图编名字。
   - `name_as_written` = 正文原样写法（必须逐字准确，照抄原文）
   - `canonical_guess` = 归并后的规范名：
     - 先查 `knownArtists`，若正文写法与某条是同一人（简繁差异、中文/日文/罗马音、昵称、错别字），**沿用该条的规范名**；
     - 查 `alias` 表能直接映射的，用映射后的规范名；
     - 确认是新画师才用新名字（新名字也填进 `canonical_guess`）。
   - `note` = 这条评论对 TA 的评价 / 提到的作品，没有就留空字符串。
3. **作品与评价**：
   - `works` = 正文明确提到的作品名（数组）；**分类为 `work_only`（只报作品、没点名画师）的评论必须填 `works`**，否则作品信息会丢失
   - 对画师的评价/提到的作品同时写进对应 `mentions` 的 `note`（网页展示用）

## 纪律

- **只处理 `review_input.json` 里 `pending` 真实存在的评论**，rpid 逐个照抄，不要写示例数据。
- **不要动任何其他文件**：不写 mentions.json / config.json / artists_raw.json / pending.json，不新建脚本。
- 合并、去重、别名回写、清队列全部由 `python scripts/merge_review.py` 程序化完成，你填完 `review.json` 就停。
- `store/review.json` 每轮**整体重写**。

## 汇报

最后用 3-5 行说明：复核了几条、分类分布、抽到哪些画师（含归并到已有条目的）、有没有新画师。不要贴长日志。
