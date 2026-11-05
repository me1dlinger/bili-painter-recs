#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""增量抓取 B 站视频评论 —— 每 12 小时跑一次用。

特性：
  * 抓一级评论（x/v2/reply/main）+ 全部楼中楼（x/v2/reply/reply）
  * 按 rpid 去重合并进 store/comments.json，已存在的只更新点赞数，不重复存
  * 新评论用「已知画师名 / 别名」做一次自动匹配，写进 store/mentions.json（标注为待复核）
  * 只保存展示需要的字段：rpid / user / content / like / rcount / ctime / isSub / root

用法：
  python scripts/fetch.py            # 抓取并合并
  python scripts/fetch.py --quiet    # 静默（cron 用）
"""
import asyncio
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STORE = os.path.join(ROOT, "store")
def _local(key, default=""):
    f = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "store", "local.json")
    if os.path.exists(f):
        return json.load(open(f, encoding="utf-8")).get(key, default)
    return default

# 运行环境（本机私有配置，见 store/local.json；不进仓库）
DUTY_HOME = os.environ.get("BILI_DUTY_HOME") or _local("dutyHome")
if not DUTY_HOME:
    raise SystemExit("缺少 BILI_DUTY_HOME：请在 store/local.json 里配置 dutyHome，或设置环境变量")
sys.path.insert(0, os.path.join(DUTY_HOME, ".venv", "lib", "python3.11", "site-packages"))

from bilibili_api import Credential, Api  # noqa: E402

BVID = "BV15cxq6tEFW"
QUIET = "--quiet" in sys.argv
# 评论总数硬上限：抓满 CAP 条即冻结该项目（多余的丢弃、不入库）。
# 目的：让网页「抓取评论 N 条」最终精确停在 CAP，不多不少。
# 冻结动作（写 store/FROZEN + 移除 crontab）由 cron_update.sh / 会话侧执行。
CAP = 1000
NOW = time.strftime("%Y-%m-%d %H:%M:%S")


def log(*a):
    if not QUIET:
        print(*a, flush=True)


def load_cred():
    c = json.load(open(os.path.join(DUTY_HOME, "bili_credential.json"), encoding="utf-8"))
    return Credential(sessdata=c["sessdata"], bili_jct=c["bili_jct"],
                      buvid3=c["buvid3"], dedeuserid=c.get("dedeuserid"))


async def api_get(url, params, cred, tries=4):
    api = {"url": url, "method": "GET", "verify": False, "params": {}}
    for a in range(tries):
        try:
            return await Api(**api, credential=cred).update_params(**params).result
        except Exception as e:
            if a == tries - 1:
                log(f"    ! {url} 失败: {str(e)[:70]}")
                return {}
            await asyncio.sleep(1.5 * (a + 1))


def slim(r, is_sub=False, root=0):
    """只保留需要的字段。"""
    m = r.get("member") or {}
    c = r.get("content") or {}
    rec = {
        "rpid": r.get("rpid"),
        "user": m.get("uname", ""),
        "content": (c.get("message") or "").strip(),
        "like": r.get("like", 0),
        "rcount": r.get("rcount", 0),
        "ctime": r.get("ctime", 0),
        "isSub": is_sub,
    }
    if is_sub:
        rec["root"] = root
    return rec


async def fetch_roots(aid, cred):
    """一级评论：两条通道都走一遍，取并集。

    2026-11-02 教训：x/v2/reply/main 只返回「热门评论池」，会**整栋漏掉**部分大热楼
    （实测漏掉一条 rcount=296 的「评论区的各位一人一个推荐画师」）。
    旧的 x/v2/reply（pn 分页）能翻到它，所以两条都跑、按 rpid 去重合并。
    """
    seen = {}

    # 通道 1：懒加载（覆盖热门池）
    nxt = 1
    while nxt <= 60:
        resp = await api_get("https://api.bilibili.com/x/v2/reply/main",
                             {"oid": aid, "type": 1, "mode": 3, "next": nxt, "ps": 30}, cred)
        reps = resp.get("replies") or []
        if not reps:
            break
        for x in reps:
            seen[x["rpid"]] = x
        if (resp.get("cursor") or {}).get("is_end"):
            break
        nxt += 1
        await asyncio.sleep(1.0)
    log(f"    通道1（懒加载）一级 {len(seen)} 条")

    # 通道 2：旧接口 pn 分页（能翻到懒加载漏掉的楼）
    pn, prev = 1, len(seen)
    while pn <= 60:
        resp = await api_get("https://api.bilibili.com/x/v2/reply",
                             {"oid": aid, "type": 1, "pn": pn, "sort": 2, "ps": 20}, cred)
        reps = resp.get("replies") or []
        if not reps:
            break
        for x in reps:
            seen[x["rpid"]] = x
        pn += 1
        await asyncio.sleep(1.0)
    log(f"    通道2（pn 分页）合计一级 {len(seen)} 条（+{len(seen) - prev}）")
    return [slim(x) for x in seen.values()]


async def fetch_subs(aid, rpid, cred):
    out, pn = [], 1
    while pn <= 30:
        resp = await api_get("https://api.bilibili.com/x/v2/reply/reply",
                             {"oid": aid, "type": 1, "root": rpid, "pn": pn, "ps": 20}, cred)
        reps = resp.get("replies") or []
        if not reps:
            break
        out.extend(slim(s, True, rpid) for s in reps)
        if len(out) >= ((resp.get("page") or {}).get("count", 0)):
            break
        pn += 1
        await asyncio.sleep(0.6)
    return out


# ---------- 自动匹配：用已知画师名/别名扫正文 ----------
def build_matcher(artists):
    pats = []
    for a in artists:
        for n in [a["name"]] + a.get("aliases", []):
            n = (n or "").strip()
            if len(n) < 2 or n in ("—",):
                continue
            pats.append((n, a["name"]))
    # 长名字优先，避免「鸟居」抢先匹配掉「鸟居ヨシツナ」
    pats.sort(key=lambda t: -len(t[0]))
    return pats


def auto_match(text, pats):
    hits, used = [], []
    for raw, canon in pats:
        if raw in text:
            # 该片段已被更长的名字覆盖则跳过
            if any(raw in u and raw != u for u in used):
                continue
            used.append(raw)
            if canon not in hits:
                hits.append(canon)
    return hits


async def main():
    cred = load_cred()
    v = await api_get("https://api.bilibili.com/x/web-interface/view", {"bvid": BVID}, cred)
    aid = v["aid"]
    claimed = (v.get("stat") or {}).get("reply", 0)
    log(f"视频: {v['title']}\naid={aid} 标称评论数={claimed}")

    roots = await fetch_roots(aid, cred)
    log(f"一级 {len(roots)} 条，抓楼中楼…")
    subs = []
    for i, r in enumerate([x for x in roots if x.get("rcount")], 1):
        s = await fetch_subs(aid, r["rpid"], cred)
        subs.extend(s)
        await asyncio.sleep(0.5)
    log(f"二级 {len(subs)} 条")

    # ---------- 合并去重 ----------
    path = os.path.join(STORE, "comments.json")
    db = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else \
        {"bvid": BVID, "aid": aid, "title": v["title"], "owner": v.get("owner", {}),
         "desc": v.get("desc", ""), "comments": {}}
    store = db["comments"]
    new_ids, updated = [], 0
    for c in roots + subs:
        k = str(c["rpid"])
        old = store.get(k)
        if not old:
            c["firstSeen"] = NOW
            store[k] = c
            new_ids.append(k)
        else:
            if old.get("like") != c.get("like") or old.get("rcount") != c.get("rcount"):
                old["like"] = c["like"]
                old["rcount"] = c["rcount"]
                updated += 1
            if old.get("content") != c["content"]:
                old["content"] = c["content"]
    store = dict(sorted(store.items(), key=lambda kv: kv[1].get("ctime", 0)))
    # ---------- 评论总数硬上限：超过 CAP 的部分丢弃、不入库 ----------
    # 保留按 ctime 升序的前 CAP 条（历史优先），本轮多出来的新评论直接不收录，
    # 同时把它们从 new_ids 里剔除，避免自动匹配 / 待复核队列引用不存在的评论。
    dropped = set()
    if len(store) > CAP:
        keep_keys = list(store.keys())[:CAP]
        keep_set = set(keep_keys)
        dropped = {k for k in store if k not in keep_set}
        store = {k: store[k] for k in keep_keys}
        new_ids = [k for k in new_ids if k not in dropped]
        log(f"已达上限 {CAP} 条：本轮多出的 {len(dropped)} 条评论不入库")
    db["comments"] = store
    db["updatedAt"] = NOW
    db["claimedReplyCount"] = claimed
    json.dump(db, open(path, "w", encoding="utf-8"), ensure_ascii=False)

    # ---------- 新评论自动匹配画师名 ----------
    mpath = os.path.join(STORE, "mentions.json")
    md = json.load(open(mpath, encoding="utf-8"))
    existing = {(str(m.get("rpid")), m.get("name_as_written")) for m in md["mentions"]}
    apath = os.path.join(ROOT, "artists_raw.json")
    artists = json.load(open(apath, encoding="utf-8")) if os.path.exists(apath) else []
    pats = build_matcher(artists)
    added = 0
    for k in new_ids:
        c = store[k]
        for canon in auto_match(c["content"], pats):
            key = (k, canon)
            if key in existing:
                continue
            md["mentions"].append({
                "root_no": 0, "commenter": c["user"], "is_sub": c["isSub"],
                "name_as_written": canon, "canonical_guess": canon,
                "context": c["content"][:100], "note": "自动匹配 · 待复核",
                "rpid": c["rpid"],
            })
            existing.add(key)
            added += 1
    md["updatedAt"] = NOW
    json.dump(md, open(mpath, "w", encoding="utf-8"), ensure_ascii=False)

    # ---------- 待 AI 复核队列（追加合并，绝不清空上一轮未复核的） ----------
    # 注意：pending 只在这里追加、由 merge_review.py 复核后清空。
    # 若覆盖式重写，下一轮 fetch 无新评论时会把还没复核的队列清掉（踩过坑）。
    ppath = os.path.join(STORE, "pending.json")
    old_pending = []
    if os.path.exists(ppath):
        old_pending = json.load(open(ppath, encoding="utf-8")).get("comments", [])
    seen_p = {str(x["rpid"]) for x in old_pending}
    fresh = []
    for k in new_ids:
        if k in seen_p:
            continue
        c = store[k]
        fresh.append({
            "rpid": c["rpid"], "user": c["user"], "content": c["content"],
            "like": c["like"], "isSub": c["isSub"], "root": c.get("root", 0),
            "autoMatched": auto_match(c["content"], pats),
        })
    pending = [x for x in (old_pending + fresh) if str(x["rpid"]) not in dropped]
    json.dump({"generatedAt": NOW, "count": len(pending), "comments": pending},
              open(ppath, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    log(f"新增 {len(new_ids)} 条评论，更新 {updated} 条，自动匹配新增提及 {added} 条")
    log(f"评论库合计 {len(store)} 条{'（已满上限 ' + str(CAP) + '，多余不入库）' if len(store) >= CAP else ''}")
    # 注意：只更新「上次抓取」这一块，published（上次发布快照）由 publish.sh 维护
    sp = os.path.join(STORE, "state.json")
    st = json.load(open(sp, encoding="utf-8")) if os.path.exists(sp) else {}
    st["lastFetch"] = {"at": NOW, "newComments": len(new_ids),
                       "updated": updated, "autoMentions": added, "total": len(store)}
    st["claimed"] = claimed
    st["total"] = len(store)
    json.dump(st, open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return len(new_ids)


if __name__ == "__main__":
    asyncio.run(main())