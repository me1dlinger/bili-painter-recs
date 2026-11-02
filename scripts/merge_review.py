#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 AI 复核结果（store/review.json）程序化合并进数据仓。

AI 只负责填 store/review.json 的结构化字段，本脚本做所有文件操作：
  1) 删除被复核评论的「自动匹配 · 待复核」占位提及
  2) 按 review 的 mentions 字段追加真实提及到 store/mentions.json
  3) 把新写法回写进 store/config.json 的 alias（仅增量，不删不改旧值）
  4) 清空 store/pending.json（复核队列）
  5) 调用 scripts/build.py 重建 data.json / md / csv（--no-build 可跳过）

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
            added += 1
            # 归并回写：已有画师的新写法 -> alias 表（下一轮自动匹配可识别）
            if g in canon_set and w != g and w not in cfg_alias:
                cfg_alias[w] = g
    m["updatedAt"] = time.strftime("%Y-%m-%d %H:%M:%S")
    json.dump(m, open(mpath, "w", encoding="utf-8"), ensure_ascii=False)

    # ---------- 3. 回写 config.json（仅增量） ----------
    json.dump(cfg, open(os.path.join(STORE, "config.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # ---------- 4. 清 pending ----------
    if not args.no_clear:
        p = os.path.join(STORE, "pending.json")
        json.dump({"generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"), "count": 0, "comments": []},
                  open(p, "w", encoding="utf-8"), ensure_ascii=False)

    print(f"mentions: {before} -> {len(m['mentions'])}（删占位 {removed}，追加 {added}，跳过 {skipped}）")
    print(f"config.alias 现共 {len(cfg_alias)} 条")

    # ---------- 5. build ----------
    if not args.no_build:
        subprocess.run([sys.executable, os.path.join(HERE, "build.py")], check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
