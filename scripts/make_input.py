#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成「AI 语义复核」的结构化入参：store/review_input.json

AI 只负责读这个文件、填 store/review.json 里的结构化字段；
不做任何文件格式操作。所有合并/去重/回写由 scripts/merge_review.py 完成。

输入：store/pending.json、artists_raw.json、store/config.json
输出：store/review_input.json（固定 schema，见文件内注释）
"""
import json
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STORE = os.path.join(ROOT, "store")


def load(name, default):
    p = os.path.join(STORE, name)
    if os.path.exists(p):
        return json.load(open(p, encoding="utf-8"))
    return default


def main():
    pending = load("pending.json", {"comments": []})
    artists = load(os.path.join(ROOT, "artists_raw.json"), [])
    cfg = load("config.json", {})

    comments = load("comments.json", {"comments": {}})["comments"]

    # 已知画师名单：规范名 + 全部别名（AI 归并判断的唯一依据）
    known = []
    for a in artists:
        known.append({"name": a["name"], "aliases": a.get("aliases", [])})

    # 给每条待复核评论附上原文定位信息，AI 不需要自己查库
    pending_out = []
    for c in pending.get("comments", []):
        rpid = str(c["rpid"])
        full = comments.get(rpid, {})
        pending_out.append({
            "rpid": c["rpid"],
            "user": c["user"],
            "content": c["content"],
            "isSub": c["isSub"],
            "root": c.get("root", 0),
            "autoMatched": c.get("autoMatched", []),   # 仅供参考，必须自行判断
        })

    out = {
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "instructions": (
            "对 pending 里每条评论做三件事：1) 分类（artist_rec/work_only/ask/chat/empty）；"
            "2) 抽正文里真实出现的画师名（每个输出一条 mentions 记录：name_as_written=原文写法，"
            "canonical_guess=归并后的规范名；若正文写法与 knownArtists 中某条目是同一人（简繁/中日/"
            "罗马音/昵称/错别字），canonical_guess 沿用该条目规范名；确认为新画师才用新名）；"
            "3) 作品/评价信息填入 note。只处理真实存在的评论，只抽正文真实出现的名字，"
            "不要凭印象补名字。输出写入 store/review.json，schema 见 merge_review.py 的说明，"
            "不要改任何其他文件。"
        ),
        "knownArtists": known,
        "alias": cfg.get("alias", {}),
        "notArtist": cfg.get("notArtist", []),
        "pending": pending_out,
        "count": len(pending_out),
    }
    with open(os.path.join(STORE, "review_input.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"review_input.json 已生成：待复核 {out['count']} 条，已知画师 {len(known)} 位")


if __name__ == "__main__":
    main()
