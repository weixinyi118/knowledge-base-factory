#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb-factory / check_kb.py — 全库体检。

检查什么（13 项，按严重程度分三级）：

  P0 必修   frontmatter 缺失 / 必填字段缺失 / level 非法 / category 与目录不符 / 双链断链
  P1 应修   companion 指向空卡 / 禁用词 / 索引漏篇 / 孤儿卡
  P2 建议   字数偏离级别区间 / 文件名不规范 / 单篇超过 1 个表格 / copyright 值非法

用法:
    python check_kb.py .              # 体检
    python check_kb.py . --fix        # 体检并自动修可修项
    python check_kb.py . --json       # 机器可读输出
    python check_kb.py . --quiet      # 只输出结论行

退出码：有 P0 返回 1，否则 0。适合挂 CI。
"""

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ZH = re.compile(r"[\u4e00-\u9fff]")
LINK = re.compile(r"\[\[([^\]]+)\]\]")
CAT_DIR = re.compile(r"^\d{2}_")
CARD_DIR = re.compile(r"(速查卡|卡片|^cards?$)", re.I)
STD_NAME = re.compile(r"^\d{2}-.+\.md$")

REQUIRED = ["title", "category", "topic", "level", "words",
            "updated", "tags", "copyright"]
# 速查卡是独立单元，没有级别/字数/子主题，字段要求不同
CARD_REQUIRED = ["title", "category", "updated", "copyright"]

LEVEL_RANGE = {"深度篇": (1500, 3200), "标准篇": (700, 1700), "速查卡": (150, 600)}
VALID_COPYRIGHT = {"可直接入库", "仅内部参考", "待确认"}

BANNED = [
    "本质是", "核心在于", "底层逻辑", "赋能", "抓手",
    "形成闭环", "生态位", "随着AI的发展", "随着 AI 的发展",
    "在当今时代", "要点一", "要点二", "首先，其次",
]
# 允许出现的上下文：当反例引用时，写作会明确标记
BANNED_ALLOW_MARK = ["❌", "禁用", "不要写", "反例", "黑名单"]
# 禁用词前面出现这些词，说明是在"教人别用"，属于提及而非使用
BANNED_NEG_PREFIX = ["不用", "别用", "不使用", "不要用", "不宜", "避免", "不许"]


# ---------------------------------------------------------------- 解析
def split_front(text):
    """返回 (head_dict, tags_list, body, ok)"""
    if not text.startswith("---"):
        return {}, [], text, False
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, [], text, False
    head_raw, body = parts[1], parts[2]
    d, tags, in_tags = {}, [], False
    for line in head_raw.split("\n"):
        if re.match(r"^\s+-\s+", line):
            if in_tags:
                tags.append(line.strip()[2:].strip())
            continue
        if ":" in line and not line.startswith((" ", "\t")):
            k, v = line.split(":", 1)
            k, v = k.strip(), v.strip()
            d[k] = v
            in_tags = (k == "tags" and v == "")
    # tags 是多行列表时 d["tags"] 为空，用收集到的列表回填，避免误判为缺字段
    if tags and not d.get("tags"):
        d["tags"] = ",".join(tags)
    return d, tags, body, True


def zh_count(text):
    return len(ZH.findall(text))


def strip_code(text):
    """去掉围栏代码块与行内代码——写在里面的 [[...]] 是示例，不是链接"""
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    return re.sub(r"`[^`\n]*`", "", text)


def table_count(body):
    """连续以 | 开头的行算一个表格"""
    n, prev = 0, False
    for line in body.split("\n"):
        cur = line.strip().startswith("|")
        if cur and not prev:
            n += 1
        prev = cur
    return n


# ---------------------------------------------------------------- 扫描
def scan(root):
    articles, cards = [], []
    for p in sorted(root.rglob("*.md")):
        rel = p.relative_to(root)
        parts = rel.parts
        if parts[0] == "tools" or len(parts) < 2:
            continue
        name = p.name
        if name.startswith("_"):
            continue
        if parts[0] == "速查卡" or CARD_DIR.search(parts[0]):
            cards.append(p)
        elif CAT_DIR.match(parts[0]):
            articles.append(p)
    return articles, cards


def load(p, root, kind):
    raw = p.read_text(encoding="utf-8", errors="replace")
    d, tags, body, ok = split_front(raw)
    return {
        "path": p,
        "rel": p.relative_to(root).as_posix(),
        "stem": p.stem,
        "dir": p.parent.name,
        "kind": kind,
        "head": d,
        "tags": tags,
        "body": body,
        "raw": raw,
        "fm_ok": ok,
        "zh": zh_count(raw),
    }


# ---------------------------------------------------------------- 检查
def check(root, do_fix=False, quiet=False):
    articles, cards = scan(root)
    A = [load(p, root, "article") for p in articles]
    C = [load(p, root, "card") for p in cards]

    names = set()
    for p in root.rglob("*.md"):
        names.add(p.stem)
        names.add(p.relative_to(root).as_posix()[:-3])

    card_names = {c["stem"] for c in C}
    issues = defaultdict(list)          # code -> [(where, detail)]
    fixed = []

    # --- 逐篇
    for it in A + C:
        h = it["head"]

        if not it["fm_ok"]:
            issues["P0.frontmatter_missing"].append((it["rel"], "文件头没有 --- 包裹的 YAML"))
            continue

        need = CARD_REQUIRED if it["kind"] == "card" else REQUIRED
        miss = [f for f in need if f not in h or not h[f]]
        if miss:
            issues["P0.field_missing"].append((it["rel"], ",".join(miss)))
            if do_fix:
                lines = it["raw"].split("\n")
                end = 1 + it["raw"].split("---")[1].count("\n")
                add = []
                for f in miss:
                    if f == "category":
                        add.append("category: " + it["dir"])
                    elif f == "title":
                        add.append("title: " + it["stem"])
                    elif f == "copyright":
                        add.append("copyright: 待确认")
                    elif f == "updated":
                        add.append("updated: 2000-01-01")
                    elif f == "words":
                        add.append("words: " + str(it["zh"]))
                if add:
                    lines[end:end] = add
                    it["path"].write_text("\n".join(lines), encoding="utf-8")
                    fixed.append((it["rel"], "补字段 " + ",".join(add)))

        lv = h.get("level", "")
        if lv and it["kind"] == "article" and lv not in ("深度篇", "标准篇"):
            issues["P0.level_invalid"].append((it["rel"], lv))

        cat = h.get("category", "")
        if cat and it["kind"] == "article" and cat != it["dir"]:
            issues["P0.category_mismatch"].append((it["rel"], f"{cat} ≠ {it['dir']}"))
            if do_fix:
                it["raw"] = re.sub(r"^category:.*$", "category: " + it["dir"],
                                   it["raw"], count=1, flags=re.M)
                it["path"].write_text(it["raw"], encoding="utf-8")
                fixed.append((it["rel"], f"category → {it['dir']}"))

        cp = h.get("copyright", "")
        if cp and cp not in VALID_COPYRIGHT:
            issues["P2.copyright_invalid"].append((it["rel"], cp))

        # companion 指向
        comp = h.get("companion", "").strip()
        if comp:
            target = comp.replace("速查卡-", "").replace("速查卡", "").strip()
            if target and target not in card_names:
                issues["P1.companion_dangling"].append((it["rel"], comp))
                if do_fix:
                    it["raw"] = re.sub(r"^companion:.*$\n?", "", it["raw"],
                                       count=1, flags=re.M)
                    it["path"].write_text(it["raw"], encoding="utf-8")
                    fixed.append((it["rel"], f"删无效 companion: {comp}"))

        # 禁用词：区分「使用」与「提及」——被引号裹住是当反例讲，不算违规
        body = it["body"]
        for b in BANNED:
            idx = body.find(b)
            while idx != -1:
                before = body[idx - 1] if idx > 0 else ""
                after = body[idx + len(b)] if idx + len(b) < len(body) else ""
                quoted = before in "\"'「『‘“《" and after in "\"'」』’”》"
                neg = body[max(0, idx - 14):idx]
                mentioned = quoted or any(n in neg for n in BANNED_NEG_PREFIX)
                ctx = body[max(0, idx - 40):idx + 40].replace("\n", " ")
                if not mentioned and not any(m in ctx for m in BANNED_ALLOW_MARK):
                    line_no = body[:idx].count("\n") + 1
                    issues["P1.banned_word"].append(
                        (it["rel"], f"L{line_no} 「{b}」 …{ctx.strip()[:40]}…"))
                    break
                idx = body.find(b, idx + 1)

        # 双链
        for m in LINK.findall(strip_code(body)):
            tgt = m.split("|")[0].split("#")[0].strip().rstrip("\\")
            if tgt and tgt not in names:
                issues["P0.broken_link"].append((it["rel"], tgt))

        # 字数
        if lv in LEVEL_RANGE:
            lo, hi = LEVEL_RANGE[lv]
            if it["zh"] < lo * 0.6 or it["zh"] > hi * 1.5:
                issues["P2.words_off"].append(
                    (it["rel"], f"{it['zh']} 字，{lv} 区间 {lo}-{hi}"))

        # 文件名
        if it["kind"] == "article" and not STD_NAME.match(it["path"].name):
            issues["P2.filename"].append((it["rel"], "应为 NN-短名.md"))

        # 表格：只放可比数字。标准篇上限 2，深度篇 3，再多就是拿表格代替论述
        tc = table_count(body)
        limit = 3 if lv == "深度篇" else 2
        if tc > limit and it["kind"] == "article":
            issues["P2.too_many_tables"].append((it["rel"], f"{tc} 个表格（上限 {limit}）"))

    # --- 索引覆盖
    for it in A:
        idx = it["path"].parent / "_分类索引.md"
        if not idx.exists():
            issues["P1.index_missing"].append((it["rel"], "分类索引文件不存在"))
            continue
        t = idx.read_text(encoding="utf-8", errors="replace")
        if it["stem"] not in t and it["head"].get("title", "###") not in t:
            issues["P1.index_unlisted"].append((it["rel"], "未出现在 _分类索引.md"))

    # --- 入口文件的双链：总目录与分类索引是唯一入口，断在这里最致命
    # （表格里的 wiki 链接会写成 [[目标\|显示名]]，转义的回车符要先剥掉）
    for p in sorted(root.rglob("*.md")):
        rel = p.relative_to(root)
        if rel.parts[0] == "tools":
            continue
        name = p.name
        if not (name.startswith("_") or name.startswith("00_")
                or name.endswith("_分类索引.md")):
            continue
        text = strip_code(p.read_text(encoding="utf-8", errors="replace"))
        for m in LINK.findall(text):
            tgt = m.split("|")[0].split("#")[0].strip().rstrip("\\")
            if tgt and tgt not in names:
                issues["P0.broken_link"].append((rel.as_posix(), tgt))

    # --- 孤儿卡
    referenced = set()
    for it in A:
        comp = it["head"].get("companion", "")
        if comp:
            referenced.add(comp.replace("速查卡-", "").replace("速查卡", "").strip())
    for c in C:
        if c["stem"].startswith("_示例"):
            continue
        if c["stem"] not in referenced and not c["head"].get("parent"):
            issues["P1.card_orphan"].append((c["rel"], "无 parent 且无正文引用"))

    # --- 输出
    total_zh = sum(x["zh"] for x in A)
    card_zh = sum(x["zh"] for x in C)
    counts = Counter(i["dir"] for i in A)

    p0 = sum(len(v) for k, v in issues.items() if k.startswith("P0"))
    p1 = sum(len(v) for k, v in issues.items() if k.startswith("P1"))
    p2 = sum(len(v) for k, v in issues.items() if k.startswith("P2"))

    if "--json" in sys.argv:
        print(json.dumps({
            "root": str(root),
            "articles": len(A), "cards": len(C),
            "words_articles": total_zh, "words_cards": card_zh,
            "by_category": dict(counts),
            "P0": p0, "P1": p1, "P2": p2,
            "fixed": [{"file": f, "what": w} for f, w in fixed],
            "issues": {k: [{"file": f, "detail": d} for f, d in v]
                       for k, v in sorted(issues.items())},
        }, ensure_ascii=False, indent=2))
        return 1 if p0 else 0

    if not quiet:
        print()
        print(f"  体检: {root}")
        print(f"  {'-' * 60}")
        print(f"  正文 {len(A)} 篇 ｜ 速查卡 {len(C)} 张 ｜ "
              f"正文 {total_zh:,} 字 ｜ 卡片 {card_zh:,} 字")
        if counts:
            dist = "  ".join(f"{k.split('_')[0]}:{v}" for k, v in sorted(counts.items()))
            print(f"  分布 {dist}")
        print()

        LABEL = {
            "P0.frontmatter_missing": "frontmatter 缺失",
            "P0.field_missing": "必填字段缺失",
            "P0.level_invalid": "level 非法",
            "P0.category_mismatch": "category 与目录不符",
            "P0.broken_link": "双链断链",
            "P1.companion_dangling": "companion 指向空卡",
            "P1.banned_word": "禁用词",
            "P1.index_missing": "分类索引缺失",
            "P1.index_unlisted": "索引漏篇",
            "P1.card_orphan": "孤儿卡",
            "P2.words_off": "字数偏离",
            "P2.filename": "文件名不规范",
            "P2.too_many_tables": "表格过多",
            "P2.copyright_invalid": "版权标签非法",
        }
        for code in sorted(issues):
            items = issues[code]
            mark = "✗" if code.startswith("P0") else ("!" if code.startswith("P1") else "·")
            print(f"  {mark} {code.split('.')[0]} {LABEL.get(code, code)} — {len(items)} 处")
            for f, d in items[:6]:
                print(f"      {f}")
                print(f"        {d}")
            if len(items) > 6:
                print(f"      … 另有 {len(items) - 6} 处")
            print()

        if fixed:
            print(f"  已自动修 {len(fixed)} 处：")
            for f, w in fixed[:8]:
                print(f"      {f} — {w}")
            print()

    verdict = "通过" if p0 == 0 and p1 == 0 else ("有必修项" if p0 else "有应修项")
    print(f"  {'-' * 60}")
    print(f"  P0 {p0} ｜ P1 {p1} ｜ P2 {p2}   →  {verdict}")
    print()
    if p0:
        print("  有 P0 说明库拿去交付会出问题（打不开的链接、筛不出来的分类）。先修 P0。")
    elif p1:
        print("  P1 不影响打开，但影响可信度：空的 companion 点开是白页，禁用词会被读者一眼看出。")
    else:
        print("  可以交付。")
    print()
    return 1 if p0 else 0


def main():
    ap = argparse.ArgumentParser(description="知识库全库体检")
    ap.add_argument("root", nargs="?", default=".", help="知识库根目录，默认当前")
    ap.add_argument("--fix", action="store_true", help="自动修可修项")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--quiet", action="store_true", help="只输出结论")
    a = ap.parse_args()

    root = Path(a.root).expanduser().resolve()
    if not root.is_dir():
        print(f"[x] 目录不存在: {root}")
        return 2
    return check(root, do_fix=a.fix, quiet=a.quiet)


if __name__ == "__main__":
    sys.exit(main())
