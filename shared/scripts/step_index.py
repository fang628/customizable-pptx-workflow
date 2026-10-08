"""Resolve checkpoint IDs from the maintained Markdown routing tables."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]


def load_step_index(root=ROOT):
    root = Path(root)
    index = {}
    for stage, relative in re.findall(
        r"^\|\s*([0-4](?:\.[123])?)\s*\|\s*\[[^\]]+\]\((stages/[^)]+/SKILL\.md)\)",
        (root / "SKILL.md").read_text(encoding="utf-8-sig"), re.M,
    ):
        entry = root / relative
        steps = []
        for identifier, target in re.findall(
            r"^\|\s*(\d\.\d[a-z](?:-\d+)?)\s*\|\s*\[[^\]]+\]\((steps/[^)]+\.md)\)",
            entry.read_text(encoding="utf-8-sig"), re.M,
        ):
            if not identifier.startswith(stage) or identifier in steps:
                raise ValueError(f"阶段 {stage} 的子步骤编号不一致：{identifier}")
            source = entry.parent / target
            heading = source.read_text(encoding="utf-8-sig").splitlines()[0]
            if not heading.startswith(f"# {identifier}："):
                raise ValueError(f"子步骤索引与文件标题不一致：{source}")
            steps.append(identifier)
        if stage in index:
            raise ValueError(f"阶段索引重复：{stage}")
        index[stage] = tuple(steps) if steps else (stage,)
    if not index:
        raise ValueError("未找到工作流阶段索引")
    return index


def validate_checkpoint(stage, step):
    allowed = load_step_index().get(stage, ())
    if step not in allowed:
        raise ValueError(f"阶段 {stage} 的有效检查点：{', '.join(allowed)}；收到：{step}")
