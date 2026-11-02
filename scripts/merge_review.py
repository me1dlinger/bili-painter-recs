#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 AI 复核结果（store/review.json）程序化合并进数据仓。

AI 只负责填 store/review.json 的结构化字段，本脚本做所有文件操作：
  1) 删除被复核评论的「自动匹配 · 待复核」占位提及
  2) 按 review 的 mentions 字段追加真实提及到 store/mentions.json
  3) work_only 评论（只报作品未点名）的 works 落盘到 config.workOnly
  4) 把新写法回写进 store/config.json 的 alias（仅增量，不删不改旧值）
  5) 清空 store/pending.json（复核队列）
  6) 调用 scripts/build.py 重建 data.json / md / csv（--no-build 可跳过）

用法：
  python scripts/merge_review.py                 # 用 store/review.json，跑完清 pending + build
  python scripts/merge_review.py --review X.json # 指定复核结果文件（测试用）
  python scripts/merge_review.py --no-clear      # 不清 pending（测试用）
  python scripts/merge_review.py --no-build      # 不调 build.py
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STORE = os.path.join(ROOT, "store")

CATEGORIES = {"artist_rec", "work_only", "ask", "chat", "empty"}


def load(p, default):
    if os.path.exists(p):
        return json.load(open(p, encoding="utf-8"))
    return default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--review", default=os.path.join(STORE, "review.json"))
    ap.add_argument("--no-clear", action="store_true")
    ap.add_argument("--no-build", action="store_true")
    args = ap.parse_args()

    review = json.load(open(args.review, encoding="utf-8"))
    comments = load(os.path.join(STORE, "comments.json"), {"comments": {}})["comments"]
    artists = load(os.path.join(ROOT, "artists_raw.json"), [])
    cfg = load(os.path.join(STORE, "config.json"), {})
    cfg_alias = cfg.setdefault("alias", {})

    rv = review.get("comments", {})
    if not rv:
        print("review.json 为空，无事可做")
        return 0

    # ---------- 1. 删占位 ----------
    mpath = os.path.join(STORE, "mentions.json")
    m = load(mpath, {"mentions": []})
    reviewed_rpids = set(rv.keys())
    before = len(m["mentions"])
    m["mentions"] = [x for x in m["mentions"]
                     if not (str(x.get("rpid")) in reviewed_rpids
                             and str(x.get("note", "")).startswith("自动匹配"))]
    removed = before - len(m["mentions"])

    # ---------- 2. 追加复核提及 ----------
    existing = {(str(x.get("rpid")), x.get("name_as_written")) for x in m["mentions"]}
    existing_canon = {(str(x.get("rpid")), x.get("canonical_guess")) for x in m["mentions"]}
    added = 0
    skipped = 0
    canon_set = {a["name"] for a in artists}
    for rpid, entry in rv.items():
        c = comments.get(str(rpid))
        if c is None:
            print(f"  ! 警告：rpid {rpid} 不在 comments.json，跳过（可能是 AI 写错 rpid）")
            skipped += 1
            continue
        mentions = entry.get("mentions")
        if mentions is None:  # 兼容旧格式：artists 数组 -> mentions
            mentions = [{"name_as_written": n, "canonical_guess": n, "note": ""}
                        for n in entry.get("artists", [])]
        for mn in mentions:
            w = (mn.get("name_as_written") or "").strip()
            g = (mn.get("canonical_guess") or "").strip()
            if not w or not g:
                continue
            key = (str(rpid), w)
            if key in existing:
                continue
            # canonical 查重：同一评论里已有同规范名的条目（无论 written 写法）则跳过，
            # 避免「老格式 artists 回退」把规范名当 written 重复追加
            if (str(rpid), g) in existing_canon:
                skipped += 1
                continue
            m["mentions"].append({
                "root_no": 0,
                "commenter": c.get("user", ""),
                "is_sub": bool(c.get("isSub")),
                "name_as_written": w,
                "canonical_guess": g,
                "context": (c.get("content") or "")[:100],
                "note": (mn.get("note") or "").strip(),
                "rpid": int(rpid),
            })
            existing.add(key)
            existing_canon.add((str(rpid), g))
            added += 1
            # 归并回写：已有画师的新写法 -> alias 表（下一轮自动匹配可识别）
            if g in canon_set and w != g and w not in cfg_alias:
                cfg_alias[w] = g
    # 仅在有实际变更时更新时间戳并写文件，避免无变更的 merge 产生 git diff
    if removed or added:
        m["updatedAt"] = time.strftime("%Y-%m-%d %H:%M:%S")
        json.dump(m, open(mpath, "w", encoding="utf-8"), ensure_ascii=False)

    # ---------- 2.5 work_only 评论的作品落盘 ----------
    # 只报作品、没点名画师的评论：works 写进 config.workOnly，
    # build.py 靠它把该评论分类为 work_only 并展示在「只推荐了作品」表格里。
    # 仅处理一级评论（build 只对一级评论生效）；楼中楼 work_only 信息留在 review.json。
    work_only_added = 0
    for rpid, entry in rv.items():
        if entry.get("category") != "work_only":
            continue
        works = entry.get("works") or []
        c = comments.get(str(rpid))
        if not works or not c or c.get("isSub"):
            continue
        wo = cfg.setdefault("workOnly", {})
        cur = wo.get(str(rpid), {})
        cur["works"] = works
        cur["resolved_by_reply"] = cur.get("resolved_by_reply")  # 保留旧值，不覆盖
        cur["desc"] = entry.get("reason") or cur.get("desc") or "只报作品名，未点名画师"
        wo[str(rpid)] = cur
        work_only_added += 1
    print(f"work_only 作品落盘 {work_only_added} 条")

    # ---------- 3. 回写 config.json（仅增量） ----------
    json.dump(cfg, open(os.path.join(STORE, "config.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # ---------- 4. 清 pending（只清本次已复核的 rpid，未复核的保留） ----------
    # 防并发：fetch 可能在本轮 merge 期间追加了新评论，若整体清空会丢复核队列
    if not args.no_clear:
        p = os.path.join(STORE, "pending.json")
        old = json.load(open(p, encoding="utf-8"))
        kept = [x for x in old.get("comments", []) if str(x["rpid"]) not in reviewed_rpids]
        json.dump({"generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
                   "count": len(kept), "comments": kept},
                  open(p, "w", encoding="utf-8"), ensure_ascii=False)

    print(f"mentions: {before} -> {len(m['mentions'])}（删占位 {removed}，追加 {added}，跳过 {skipped}）")
    print(f"config.alias 现共 {len(cfg_alias)} 条")

    # ---------- 5. build ----------
    if not args.no_build:
        subprocess.run([sys.executable, os.path.join(HERE, "build.py")], check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
