#!/usr/bin/env python3
"""Initialize an additive workspace for the editable PPTX workflow."""

from __future__ import annotations

import argparse
import json
import shutil
import re
from datetime import datetime, timezone
from pathlib import Path


STAGES = ["0", "1.1", "1.2", "1.3", "2.1", "2.2", "3.1", "3.2", "3.3", "4"]

DIRECTORIES = [
    "00_intake/materials/reports",
    "00_intake/materials/papers",
    "00_intake/materials/photos",
    "00_intake/materials/promo",
    "00_intake/materials/brand",
    "00_intake/materials/data",
    "00_intake/materials/other",
    "01_inventory",
    "02_design",
    "02_design/generated-assets",
    "03_concepts/option-a",
    "03_concepts/option-b",
    "03_concepts/option-c",
    "03_concepts/prompts",
    "03_concepts/assets",
    "04_full-preview/assets",
    "04_full-preview/slides",
    "05_reconstruction/photos",
    "05_reconstruction/vectors",
    "05_reconstruction/rasters",
    "05_reconstruction/cutouts",
    "06_build",
    "07_delivery/preview",
    "07_delivery/review",
    "08_speaker-notes",
]


def skill_root() -> Path:
    return Path(__file__).resolve().parents[3]


def copy_if_missing(source: Path, destination: Path, created: list[str]) -> None:
    if destination.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() == ".md":
        text = source.read_text(encoding="utf-8-sig")
        def resolve_link(match):
            label, target = match.group(1), match.group(2)
            path_part, separator, fragment = target.partition("#")
            if not path_part or re.match(r"^[a-zA-Z]+:", path_part):
                return match.group(0)
            resolved = (source.parent / path_part.strip("<>")).resolve()
            if not resolved.exists():
                return match.group(0)
            absolute = resolved.as_posix() + (separator + fragment if separator else "")
            return f"[{label}](<{absolute}>)"
        text = re.sub(r"\[([^\]]*)\]\(([^\n]+?)\)", resolve_link, text)
        destination.write_text(text, encoding="utf-8")
    else:
        shutil.copyfile(source, destination)
    created.append(str(destination))


def write_if_missing(destination: Path, content: str, created: list[str]) -> None:
    if destination.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")
    created.append(str(destination))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", help="Directory to initialize")
    args = parser.parse_args()

    project = Path(args.project_dir).expanduser().resolve()
    root = skill_root()
    project.mkdir(parents=True, exist_ok=True)
    for relative in DIRECTORIES:
        (project / relative).mkdir(parents=True, exist_ok=True)

    created: list[str] = []
    copies = {
        root / "stages/11-intake/assets/project-brief.md": project / "00_intake/project-brief.md",
        root / "stages/11-intake/assets/material-inventory.md": project / "01_inventory/material-inventory.md",
        root / "stages/13-design/assets/design-spec.md": project / "02_design/design-spec.md",
        root / "stages/21-concepts/assets/concept-review.md": project / "03_concepts/concept-review.md",
        root / "stages/31-element-audit/assets/element-inventory.md": project / "05_reconstruction/element-inventory.md",
        root / "stages/31-element-audit/assets/slide-elements.md": project / "05_reconstruction/slide-elements.md",
        root / "stages/33-build/assets/deck-spec.json": project / "06_build/deck-spec.json",
    }
    for source, destination in copies.items():
        copy_if_missing(source, destination, created)

    state_path = project / "workflow-state.json"
    if not state_path.exists():
        state = {
            "workflow": "pptx-workflow",
            "version": 2,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "stages": {
                stage: {
                    "status": "complete" if stage == "0" else "not_started",
                    "updated_at": datetime.now(timezone.utc).isoformat() if stage == "0" else None,
                    "notes": "项目骨架已初始化。" if stage == "0" else "",
                }
                for stage in STAGES
            },
        }
        state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        created.append(str(state_path))

    image_config = {
        "version": 1,
        "provider": "imagegen",
        "model": "builtin-auto",
        "credentialEnv": "",
        "credentialsReady": False,
        "allowReferenceUpload": False,
        "referenceImageLimit": 3,
        "adapterScript": "",
        "adapterPython": "",
        "adapterArguments": {
            "prompt": "--prompt",
            "model": "--model",
            "size": "--size",
            "count": "--n",
            "seed": "--seed",
            "outputDir": "--output-dir",
            "image": "--image",
        },
        "notes": "默认使用 imagegen skill 的内置 image_gen 工具，无需 API Key；builtin-auto 是工具路由标记，不是实际模型名称。阶段1.1确认工具可用性、用户需求及参考图许可后标记就绪。仅用户明确选择外部 CLI/API 时才配置供应商、模型、密钥和适配脚本；内置工具不可用时不得静默切换。",
    }
    write_if_missing(
        project / "00_intake/ai-image-config.json",
        json.dumps(image_config, indent=2, ensure_ascii=False) + "\n",
        created,
    )
    write_if_missing(
        project / "03_concepts/approved-direction.md",
        "# 已确认的视觉方向\n\n- 状态：等待用户\n- 选定方案：\n- 修改要求：\n- 确认日期：\n",
        created,
    )
    write_if_missing(
        project / "04_full-preview/generation-log.md",
        "# 完整预览生成日志\n\n| 页面 | 模型与版本 | 提示词与种子 | 参考材料 | 输出 | 说明 |\n|---|---|---|---|---|---|\n",
        created,
    )
    write_if_missing(project / "06_build/build-log.md", "# 构建日志\n\n", created)
    for relative, data in {
        "01_inventory/materials.json": {"materials": []},
        "02_design/content.json": {
            "include_toc": True,
            "progress_bar": {
                "enabled": True,
                "exclude_page_types": ["title", "toc"],
            },
            "slides": [],
        },
        "02_design/claim-map.json": {"version": 1, "slides": []},
        "02_design/generated-assets.json": {"version": 1, "assets": []},
        "02_design/image-intent-plan.json": {
            "version": 1,
            "canvas": {"width": 1920, "height": 1080, "unit": "px", "aspect": "16:9"},
            "slides": [],
        },
        "02_design/image-plan.json": {
            "version": 1,
            "canvas": {"width": 1920, "height": 1080, "unit": "px", "aspect": "16:9"},
            "slides": [],
        },
        "05_reconstruction/assets.json": {"assets": []},
        "03_concepts/generation-jobs.json": {
            "note": "不设次数预算：每任务本轮默认重试 8 次，可用 --attempts 调整。",
            "jobs": [],
        },
        "04_full-preview/generation-jobs.json": {
            "note": "不设次数预算：每任务本轮默认重试 8 次，可用 --attempts 调整。",
            "jobs": [],
        },
    }.items():
        write_if_missing(project / relative, json.dumps(data, indent=2, ensure_ascii=False) + "\n", created)
    write_if_missing(
        project / "07_delivery/qa-report.md",
        "# 质量检查报告\n\n- 结构检查：未执行\n- 成品与已批准预览的一致性：未执行\n- 内容检查：未执行\n- 美学评审：阶段 2.2 完成后记录\n- 渲染器与版本：未记录\n- 已知限制：待填写\n",
        created,
    )

    print(json.dumps({"project": str(project), "created": created, "created_count": len(created)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
