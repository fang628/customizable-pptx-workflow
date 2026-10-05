#!/usr/bin/env python3
"""Copy the 分块参考图 a deck needs into the project, ready for the preview jobs.

Usage: python prepare_split_references.py <project>

Reads 02_design/design-spec.md (《页面分块要求》表) and the shared split reference
index, copies every matched reference image into 02_design/split-references/<id>/,
and writes 02_design/split-references.json. 阶段 2.1／2.2 的整页预览任务把这些路径写进
references，参考图就与设计提示词一起交给 AI。
"""

import argparse
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared/scripts"))
from workflow_lib import (  # noqa: E402
    SPLIT_REFERENCE_INDEX,
    page_split_rows,
    read_json,
    split_entries,
    split_reference_path,
)

REFERENCE_ROOT = "02_design/split-references"
MANIFEST = "02_design/split-references.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir")
    args = parser.parse_args()
    project = Path(args.project_dir).expanduser().resolve()

    spec_path = project / "02_design/design-spec.md"
    if not spec_path.is_file():
        raise SystemExit(f"缺少设计稿：{spec_path}")
    if not SPLIT_REFERENCE_INDEX.is_file():
        raise SystemExit(f"缺少分块参考图索引：{SPLIT_REFERENCE_INDEX}")
    page_type = {}
    content_path = project / "02_design/content.json"
    if content_path.is_file():
        content = read_json(content_path)
        page_type = {slide["id"]: slide.get("page_type") for slide in content.get("slides", [])}

    pages = []
    copies = 0
    for page_id, cell in page_split_rows(spec_path.read_text(encoding="utf-8-sig")):
        if page_type.get(page_id) == "title":
            continue
        entries = split_entries(cell)
        if not entries:
            continue
        references = []
        for entry in entries:
            target_dir = project / REFERENCE_ROOT / entry["id"]
            target_dir.mkdir(parents=True, exist_ok=True)
            for name in entry["files"]:
                source = SPLIT_REFERENCE_INDEX.parent / name
                if not source.is_file():
                    raise SystemExit(f"参考图缺失：{source}")
                target = target_dir / name
                if not target.is_file() or target.read_bytes() != source.read_bytes():
                    shutil.copyfile(source, target)
                    copies += 1
            references.append(split_reference_path(entry))
        pages.append({
            "id": page_id,
            "splits": [entry["name"] for entry in entries],
            "labels": [entry["label"] for entry in entries],
            "references": references,
        })

    manifest = {
        "version": 1,
        "generatedFrom": "02_design/design-spec.md",
        "skillIndex": "shared/references/splits/index.json",
        "pages": pages,
    }
    (project / MANIFEST).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "pages": len(pages),
        "copied": copies,
        "manifest": MANIFEST,
        "references": {page["id"]: page["references"] for page in pages},
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
