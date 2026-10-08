"""Read selected Markdown sections/pages with an explicit character ceiling."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import sys


def sections(text):
    # Ignore headings inside fenced code examples.
    lines = text.splitlines(keepends=True)
    starts, offset, fence = [], 0, None
    for line in lines:
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            if fence is None:
                fence = marker[1][0]
            elif marker[1][0] == fence:
                fence = None
        if fence is None:
            match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
            if match:
                starts.append((len(match[1]), match[2], offset))
        offset += len(line)
    result = []
    for index, (level, title, start) in enumerate(starts):
        end = next((p for lev, _, p in starts[index + 1:] if lev <= level), len(text))
        result.append((title, text[start:end]))
    return result


def select(text, names=None, page=None):
    indexed = sections(text)
    if page:
        names = [title for title, _ in indexed if re.match(re.escape(page) + r"(?:\s|[：:—-]|$)", title)]
        if not names:
            raise ValueError(f"未找到页面章节 {page}，请先 --list；不能用整份文件代替")
    if not names:
        return text
    selected = []
    for name in names:
        matches = [body for title, body in indexed if title == name]
        if len(matches) != 1:
            raise ValueError(f"章节名称不存在或不唯一：{name}；请先 --list")
        selected.append(matches[0])
    return "\n".join(selected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--section", action="append")
    parser.add_argument("--page")
    parser.add_argument("--max-chars", type=int, default=12000)
    args = parser.parse_args()
    text = args.path.read_text(encoding="utf-8-sig")
    if args.list:
        print(f"文件 SHA-256：{hashlib.sha256(args.path.read_bytes()).hexdigest()}")
        for title, body in sections(text):
            print(f"{len(body):6} 字符  {title}  SHA-256={hashlib.sha256(body.encode('utf-8')).hexdigest()}")
        return
    selected = select(text, args.section, args.page)
    if len(selected) > args.max_chars:
        raise ValueError(f"选取内容为 {len(selected)} 字符，超过本次 {args.max_chars} 字符上限；"
                         "请按子章节或页面继续拆分，不截断规范")
    print(selected)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        sys.exit(1)
