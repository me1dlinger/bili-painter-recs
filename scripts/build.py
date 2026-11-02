#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""由 store/ 重新生成画师榜与网页数据。

输入：store/comments.json、store/mentions.json、store/config.json
输出：artists_raw.json、data.json、画师推荐榜.md、画师推荐榜.csv

每次 fetch.py 跑完都执行一次即可。
"""
import collections
import csv
import unicodedata
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
S = lambda *p: os.path.join(ROOT, *p)

store = json.load(open(S("store", "comments.json"), encoding="utf-8"))
mstore = json.load(open(S("store", "mentions.json"), encoding="utf-8"))
cfg = json.load(open(S("store", "config.json"), encoding="utf-8"))

ALIAS = cfg["alias"]
NOT_ARTIST = set(cfg["notArtist"])
LOW_CONF = set(cfg["lowConf"])
WORKS = cfg["works"]
WORK_ONLY = cfg["workOnly"]

# AI 语义复核结果（存在时优先于正则规则）
REVIEW = ({}
          if not os.path.exists(S("store", "review.json"))
          else json.load(open(S("store", "review.json"), encoding="utf-8")).get("comments", {}))

# 名字归一：全角转半角 + 去掉空格与常见标点 + 忽略大小写
# 用于兜住「92M / 92m」「Ｃｒｏｒｉｉｎ / Croriin」这类纯写法差异
def _key(n):
    n = unicodedata.normalize("NFKC", n or "")
    n = re.sub(r"[\s·・._\-,、。！!？?（）()\[\]「」『』＆&~〜]", "", n)
    return n.lower()

comments = list(store["comments"].values())
for c in comments:
    c["user"] = c.get("user", "")
roots = sorted([c for c in comments if not c["isSub"]], key=lambda r: (-r["like"], r.get("ctime", 0), r["rpid"]))
for i, r in enumerate(roots, 1):
    r["rootNo"] = i
no_of = {r["rpid"]: r["rootNo"] for r in roots}
name_of = {r["rpid"]: r["user"] for r in roots}
subs = [c for c in comments if c["isSub"]]
for c in subs:
    c["rootNo"] = no_of.get(c.get("root"), 0)
    c["rootUser"] = name_of.get(c.get("root"), "")
allc = roots + subs
by_rpid = {c["rpid"]: c for c in allc}


def norm(t):
    return re.sub(r"\s+", "", t or "")


def canon(name):
    return ALIAS.get((name or "").strip(), (name or "").strip())


# ---------- 提及 -> 评论 ----------
def locate(m):
    """把一条提及定位回原评论。优先 rpid；否则按「同一用户 + 主/子评论 + 正文片段」匹配。"""
    if m.get("rpid") and int(m["rpid"]) in by_rpid:
        return by_rpid[int(m["rpid"])]
    ctx = norm(m.get("context"))
    user = m.get("commenter")
    isub = bool(m.get("is_sub"))
    same = [c for c in allc if c["user"] == user and c["isSub"] == isub]
    pool = same or [c for c in allc if c["user"] == user]
    # 1) 正文片段命中
    if ctx:
        for c in pool:
            n = norm(c["content"])
            if n and (ctx[:24] in n or n[:24] in ctx):
                return c
    # 2) 序号 + 用户命中
    for c in pool:
        if c["rootNo"] == m.get("root_no"):
            return c
    if pool:
        return pool[0]
    # 3) 最后按正文片段全局找
    if ctx:
        for c in allc:
            if ctx[:24] and ctx[:24] in norm(c["content"]):
                return c
    return None


mention_by_comment = collections.defaultdict(list)
groups = collections.defaultdict(list)
unmatched = 0
for m in mstore["mentions"]:
    written = (m.get("name_as_written") or "").strip()
    guess = (m.get("canonical_guess") or "").strip()
    key = canon(guess or written)
    if not key or key in NOT_ARTIST:
        continue
    c = locate(m)
    if c is None:
        unmatched += 1
        continue
    art = {
        "artist": key, "written": written, "note": (m.get("note") or "").strip(),
        "rootNo": c["rootNo"], "isSub": c["isSub"], "user": c["user"], "rpid": c["rpid"],
    }
    mention_by_comment[c["rpid"]].append(art)
    groups[key].append(art)

# 兜底归并：把只看大小写/空格/符号差异的名字合成一条（如 92m / 92M）
MERGED = []
merged = {}
for name, ms in groups.items():
    merged.setdefault(_key(name), []).append((name, ms))
groups = {}
for k, pairs in merged.items():
    if len(pairs) == 1:
        groups[pairs[0][0]] = pairs[0][1]
    else:
        pairs.sort(key=lambda t: -len(t[1]))          # 以提及最多的写法为准
        keep = pairs[0][0]
        for n, ms in pairs[1:]:
            for m in ms:
                m["written"] = m["written"] or n
            pairs[0][1].extend(ms)
        groups[keep] = pairs[0][1]
        MERGED.append(f'{" / ".join(n for n, _ in pairs)} → {keep}')

artists_raw = []
for name, ms in groups.items():
    users = {m["user"] for m in ms if m["user"]}
    aliases = sorted({m["written"] for m in ms if m["written"] and m["written"] != name})
    artists_raw.append({
        "name": name, "aliases": aliases, "mentions": len(ms), "users": len(users),
        "lowConfidence": name in LOW_CONF,
        "notes": [],  # 由 data.json 阶段补全
        "evidence": [{"commenter": m["user"], "isSub": m["isSub"], "written": m["written"],
                      "context": "", "note": m["note"]} for m in ms],
        "_raw": ms,
    })
artists_raw.sort(key=lambda a: (-a["mentions"], -a["users"], a["name"]))
json.dump(artists_raw, open(S("artists_raw.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# ---------- 分类 ----------
ASK_PAT = re.compile(r"(求|有没有|哪位|是谁|叫啥|叫什么|推荐一下|来点|求个|求车牌|有jm号|数字吗|作者名|什么作者|车牌)")
EMPTY_PAT = re.compile(r"^[\s\W\d]*$")
cat = {}
for c in allc:
    rv = REVIEW.get(str(c["rpid"]))
    if rv and rv.get("category"):
        cat[c["rpid"]] = rv["category"]
        continue
    text = (c["content"] or "").strip()
    ms = mention_by_comment.get(c["rpid"], [])
    if ms:
        cat[c["rpid"]] = "artist_rec"
    elif len(text) <= 2 or EMPTY_PAT.match(text) or (text.startswith("@") and len(text) < 30):
        cat[c["rpid"]] = "empty"
    elif not c["isSub"] and str(c["rpid"]) in WORK_ONLY:
        cat[c["rpid"]] = "work_only"
    elif ASK_PAT.search(text):
        cat[c["rpid"]] = "ask"
    else:
        cat[c["rpid"]] = "chat"

# ---------- 输出 ----------
works_by_artist = collections.defaultdict(list)
for w in WORKS:
    works_by_artist[w["artist"]].append(w["title"])

artists_out = []
for a in artists_raw:
    ev = []
    for m in a["_raw"]:
        c = by_rpid.get(m["rpid"])
        note = m["note"]
        ev.append({"rpid": m.get("rpid"), "commenter": m["user"], "isSub": m["isSub"],
                   "written": m["written"],
                   "context": (note if note.startswith("自动匹配") else (m.get("context") or ""))[:140],
                   "note": ("" if note.startswith("自动匹配") else note)})
    notes, seen = [], set()
    for m in a["_raw"]:
        n = m["note"].strip()
        if n and not n.startswith("自动匹配") and n not in seen and len(n) > 2:
            seen.add(n)
            notes.append(n)
    artists_out.append({
        "name": a["name"], "aliases": a["aliases"], "mentions": a["mentions"], "users": a["users"],
        "lowConfidence": a["lowConfidence"], "notes": notes[:8], "evidence": ev,
    })

cat_stats = collections.Counter(cat.values())


def _update_meta(out_stats, artist_names, work_items):
    """给前端用的更新信息：抓取时间 + 相对「上次发布」的变化量。

    state.json 里 published 是上次推到线上时的快照，所以差值反映的是
    「用户这次刷新页面，能比上次多看到什么」——不管变化来自定时抓取、
    手动补抓还是 AI 复核。
    自 2026-11-02 起快照还带 artistNames / workTitles，据此算出
    newArtists / newWorks 列表（新增画师、新增作品），供前端弹窗展示。
    """
    sp = S("store", "state.json")
    st = json.load(open(sp, encoding="utf-8")) if os.path.exists(sp) else {}
    f = st.get("lastFetch", {})
    pub = st.get("published", {})
    d_comments = out_stats["comments"] - pub.get("comments", out_stats["comments"])
    d_artists = out_stats["artists"] - pub.get("artists", out_stats["artists"])
    d_mentions = out_stats["mentions"] - pub.get("mentions", out_stats["mentions"])
    # 新增列表：没有快照基准（旧 state）时不给列表，避免把全量当新增
    pub_names = set(pub.get("artistNames", []))
    pub_works = set(pub.get("workTitles", []))
    new_artists = [n for n in artist_names if n not in pub_names] if pub_names else []
    new_works = [w for w in work_items if w["title"] not in pub_works] if pub_works else []
    return {
        "lastFetchAt": f.get("at", ""),
        "lastFetchNew": f.get("newComments", 0),
        "publishedAt": pub.get("at", ""),
        "delta": {"comments": d_comments, "artists": d_artists, "mentions": d_mentions},
        "newArtists": new_artists,
        "newWorks": new_works,
    }
out = {
    "meta": {
        "title": store["title"], "bvid": store["bvid"], "aid": store["aid"],
        "owner": store.get("owner", {}), "desc": store.get("desc", ""),
        "fetchedAt": store.get("updatedAt", ""), "claimedReplyCount": store.get("claimedReplyCount", 0),
        "rootCount": len(roots), "subCount": len(subs), "totalCount": len(allc),
        "update": _update_meta(out_stats={"comments": len(allc), "artists": len(artists_out),
                                          "mentions": sum(a["mentions"] for a in artists_out)},
                               artist_names=[a["name"] for a in artists_out],
                               work_items=WORKS),
    },
    "stats": {"categories": dict(cat_stats), "artistCount": len(artists_out),
              "mentionCount": sum(a["mentions"] for a in artists_out)},
    "artists": artists_out,
    "works": WORKS,
    "comments": [{
        "rpid": c["rpid"], "rootNo": c["rootNo"], "isSub": c["isSub"], "user": c["user"], "like": c["like"],
        "ctime": c.get("ctime", 0), "firstSeen": c.get("firstSeen", ""),
        "content": c["content"], "category": cat.get(c["rpid"], "chat"),
        "artists": mention_by_comment.get(c["rpid"], []),
        "workInfo": WORK_ONLY.get(str(c["rpid"])) if not c["isSub"] else None,
        "rootUser": c.get("rootUser", ""),
    } for c in allc],
}
json.dump(out, open(S("data.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# CSV / MD
with open(S("画师推荐榜.csv"), "w", encoding="utf-8-sig", newline="") as f:
    wr = csv.writer(f)
    wr.writerow(["排名", "画师", "别名", "提及次数", "推荐人数", "评论里的作品", "评论里的评价", "低置信"])
    for i, a in enumerate(artists_out, 1):
        wr.writerow([i, a["name"], " / ".join(a["aliases"]), a["mentions"], a["users"],
                     " ; ".join(works_by_artist.get(a["name"], [])), " ; ".join(a["notes"]),
                     "是" if a["lowConfidence"] else ""])

L = []
add = L.append
add("# B站评论区画师推荐分析\n")
add(f"**视频**：《{out['meta']['title']}》\n")
add(f"- BV号：{out['meta']['bvid']}　UP主：{out['meta']['owner'].get('name','')}")
add(f"- 数据更新时间：{out['meta']['fetchedAt']}")
add(f"- 抓取评论：一级 {out['meta']['rootCount']} 条 + 二级（楼中楼）{out['meta']['subCount']} 条 = **{out['meta']['totalCount']} 条**")
add(f"- 视频页面标称评论数 {out['meta']['claimedReplyCount']}（差额属平台计数口径／已删除或风控隐藏）")
add(f"- 去重后画师：**{out['stats']['artistCount']} 位**，累计被提及 **{out['stats']['mentionCount']} 次**\n")
add("## 一、评论分类总览\n")
add("| 分类 | 条数 | 说明 |")
add("| --- | ---: | --- |")
for k, label, desc in [("artist_rec", "画师推荐", "评论正文直接点名了画师"),
                       ("work_only", "推荐作品（未点名画师）", "只报作品／配图描述；部分由楼中楼补出画师名"),
                       ("ask", "求推荐 / 提问", "求车牌、求作者名、求推荐"),
                       ("chat", "普通评论", "感慨、玩梗、点评平台"),
                       ("empty", "无实质内容", "@某人、表情、单字、纯数字")]:
    add(f"| {label} | {cat_stats.get(k,0)} | {desc} |")
add("")
add("一位推荐者在一条评论里列出一串画师时，每个画师各计一次；同一画师被多人推荐则累计。")
add("「提及次数」是评论里出现的次数，「推荐人数」是提到该画师的不同用户数。\n")
add("## 二、画师推荐榜（去重 + 提及次数）\n")
add("| # | 画师 | 别名 | 提及次数 | 推荐人数 | 评论里提到的作品 | 评论里的评价 |")
add("| ---: | --- | --- | ---: | ---: | --- | --- |")
for i, a in enumerate(artists_out, 1):
    nm = a["name"] + ("（低置信）" if a["lowConfidence"] else "")
    add(f"| {i} | {nm} | {' / '.join(a['aliases']) or '—'} | {a['mentions']} | {a['users']} | "
        f"{' / '.join(works_by_artist.get(a['name'], [])) or '—'} | {('；'.join(a['notes'][:4]) or '—').replace('|','／')} |")
add("")
add("## 三、评论区提到的作品／系列\n")
add("| 作品 / 系列 | 对应画师 | 评论里的说明 |")
add("| --- | --- | --- |")
for w in WORKS:
    add(f"| {w['title']} | {w['artist']} | {w['note'].replace('|','／')} |")
add("")
add("## 四、只推荐了作品、没点名画师的评论\n")
add("| 编号 | 评论人 | 原文 | 处理结果 |")
add("| ---: | --- | --- | --- |")
for c in out["comments"]:
    if c["category"] == "work_only":
        info = c["workInfo"] or {}
        add(f"| #{c['rootNo']} | {c['user']} | {c['content'].replace('|','／')[:60]} | {info.get('desc','')} |")
add("")
add("## 五、提及次数 5 次及以上的画师（详细条目）\n")
for a in artists_out:
    if a["mentions"] < 5:
        continue
    add(f"### {a['name']}　提及 {a['mentions']} 次 / {a['users']} 位推荐者")
    if a["aliases"]:
        add(f"- 别名写法：{' / '.join(a['aliases'])}")
    if a["lowConfidence"]:
        add("- 备注：低置信项，疑似社团名或简称，请自行核对")
    if works_by_artist.get(a["name"]):
        add(f"- 评论里提到的作品：{' / '.join(works_by_artist[a['name']])}")
    if a["notes"]:
        add("- 评论里的评价：")
        for n in a["notes"]:
            add(f"  - {n}")
    add("- 原始评论证据（节选）：")
    for e in a["evidence"][:6]:
        add(f"  - [{'楼中楼' if e['isSub'] else '一级评论'}] {e['commenter']}：{e['context'][:100]}")
    add("")
open(S("画师推荐榜.md"), "w", encoding="utf-8").write("\n".join(L))

if MERGED:
    print("写法归并:", "；".join(MERGED))
print(f"评论 {len(allc)}（一级 {len(roots)} / 二级 {len(subs)}）｜画师 {len(artists_out)} 位｜提及 {out['stats']['mentionCount']} 次｜未匹配提及 {unmatched}")
print("分类:", dict(cat_stats))