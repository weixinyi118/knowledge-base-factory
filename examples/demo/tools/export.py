#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb-factory / export_kb.py — 导出篇目清单并打包交付。

做两件事:
    1. 生成 _篇目清单.csv（UTF-8 BOM，Excel 双击不乱码，12 列）
    2. 打包 zip（结构干净，无 .DS_Store / __pycache__）

用法:
    python export_kb.py .                      # 清单 + 打包到桌面
    python export_kb.py . --dest ./dist        # 指定输出目录
    python export_kb.py . --csv-only           # 只要清单
    python export_kb.py . --zip-only --version v5
"""

import argparse
import csv
import os
import re
import sys
import zipfile
from collections import Counter
from datetime import date
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ZH = re.compile(r"[\u4e00-\u9fff]")
CAT_DIR = re.compile(r"^\d{2}_")
SKIP_DIRS = {"__pycache__", ".git", ".obsidian", "node_modules", ".idea", ".vscode"}
SKIP_FILES = {".DS_Store", "Thumbs.db", "desktop.ini"}

COLUMNS = ["类型", "分类", "序号", "简称", "标题", "级别",
           "字数", "主题", "标签", "版权", "配套卡", "路径"]


def split_front(text):
    if not text.startswith("---"):
        return {}, [], text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, [], text
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
    if tags and not d.get("tags"):
        d["tags"] = ",".join(tags)
    return d, tags, body


def collect(root):
    rows = []
    for p in sorted(root.rglob("*.md")):
        rel = p.relative_to(root)
        parts = rel.parts
        if len(parts) < 2 or parts[0] in SKIP_DIRS:
            continue
        if p.name.startswith("_"):
            continue
        is_card = parts[0] == "速查卡"
        if not is_card and not CAT_DIR.match(parts[0]):
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        d, tags, _ = split_front(text)
        stem = p.stem
        rows.append({
            "类型": "速查卡" if is_card else "正文",
            "分类": d.get("category", parts[0] if not is_card else ""),
            "序号": stem[:2] if not is_card else "",
            "简称": stem if is_card else stem[3:],
            "标题": d.get("title", stem),
            "级别": "速查卡" if is_card else d.get("level", ""),
            "字数": len(ZH.findall(text)),
            "主题": d.get("topic", ""),
            "标签": "|".join(tags),
            "版权": d.get("copyright", ""),
            "配套卡": d.get("companion", "").replace("速查卡-", ""),
            "路径": rel.as_posix(),
        })
    rows.sort(key=lambda r: (0 if r["类型"] == "正文" else 1,
                             r["分类"], r["序号"]))
    return rows


def guess_desktop():
    for c in [Path.home() / "Desktop", Path.home() / "桌面",
              Path.home() / "OneDrive" / "Desktop"]:
        if c.is_dir():
            return c
    return Path.home()


def write_csv(root, rows):
    out = root / "_篇目清单.csv"
    try:
        with open(out, "w", encoding="utf-8-sig", newline="") as fp:
            w = csv.DictWriter(fp, fieldnames=COLUMNS)
            w.writeheader()
            for r in rows:
                w.writerow({c: r[c] for c in COLUMNS})
    except PermissionError:
        print(f"[!] 写不进去：{out.name} 正被其他程序占用（Excel / WPS / 预览）。")
        print("    关掉它再跑一次。清单内容没变，跳过这一步。")
        return None
    return out


def make_zip(root, dest, version, name):
    dest.mkdir(parents=True, exist_ok=True)
    tag = f"_{version}" if version else ""
    out = dest / f"{name}{tag}_{date.today().strftime('%Y%m%d')}.zip"
    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in sorted(root.rglob("*")):
            if p.is_dir():
                continue
            rel = p.relative_to(root)
            if any(part in SKIP_DIRS for part in rel.parts):
                continue
            if p.name in SKIP_FILES:
                continue
            if p.name.startswith(".") and p.name != ".gitignore":
                continue
            if p.suffix == ".zip":
                continue
            z.write(p, f"{name}/{rel.as_posix()}")
            n += 1
    return out, n


def main():
    ap = argparse.ArgumentParser(description="导出篇目清单并打包")
    ap.add_argument("root", nargs="?", default=".", help="知识库根目录")
    ap.add_argument("--dest", help="zip 输出目录，默认桌面")
    ap.add_argument("--version", default="", help="版本号，如 v5")
    ap.add_argument("--name", help="包内顶层目录名，默认取库目录名")
    ap.add_argument("--csv-only", action="store_true")
    ap.add_argument("--zip-only", action="store_true")
    a = ap.parse_args()

    root = Path(a.root).expanduser().resolve()
    if not root.is_dir():
        print(f"[x] 目录不存在: {root}")
        return 2
    name = a.name or root.name

    rows = collect(root)
    art = [r for r in rows if r["类型"] == "正文"]
    card = [r for r in rows if r["类型"] == "速查卡"]

    if not a.zip_only:
        out = write_csv(root, rows)
        if out:
            print(f"[ok] 清单 {out.name} — {len(rows)} 行（正文 {len(art)} / 卡 {len(card)}）")

    if not a.csv_only:
        dest = Path(a.dest).expanduser() if a.dest else guess_desktop()
        try:
            z, n = make_zip(root, dest, a.version, name)
        except PermissionError as e:
            print(f"[!] 打包失败：{e.filename} 被占用，关掉再试。")
            return 1
        size = os.path.getsize(z) / 1024 / 1024
        print(f"[ok] 打包 {z}")
        print(f"     {n} 个文件 ｜ {size:.2f} MB")

    # 统计
    aw = sum(r["字数"] for r in art)
    cw = sum(r["字数"] for r in card)
    print()
    print(f"  正文 {len(art)} 篇 / {aw:,} 字 ｜ 速查卡 {len(card)} 张 / {cw:,} 字")
    print(f"  合计 {len(rows)} 个内容单元 / {aw + cw:,} 字")
    dist = Counter(r["分类"] for r in art)
    if dist:
        print("  分类：" + "  ".join(f"{k.split('_')[0]}:{v}" for k, v in sorted(dist.items())))
    empty = [c for c in COLUMNS if any(not r[c] for r in rows)]
    if empty:
        print(f"  注意：以下列存在空值 — {', '.join(empty)}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
