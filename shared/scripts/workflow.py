#!/usr/bin/env python3
"""Register materials, record real user approvals, and track stage versions."""

import argparse
import json
from pathlib import Path
import sys

from workflow_lib import (
    STAGES, STOP_POINTS, ai_image_config_errors, approval_errors, collect,
    design_errors, digest, gate_errors, generation_evidence_errors,
    generation_jobs_errors, generation_ledger_errors, generation_prompts_errors,
    content_plan_errors,
    deck_style_errors,
    material_errors, now, page_versions, preview_pages_errors,
    read_json, referenced_generation_files, speaker_script_errors,
    schema_errors, stop_point_errors, stop_point_label, stop_point_status,
    project_lock, write_json,
)
from preview_images import stage_preview_errors


def portable(project, path):
    path = path.resolve()
    return path.relative_to(project).as_posix() if path.is_relative_to(project) else str(path)


def complete(project, stage):
    if stage == "0":
        return
    index = STAGES.index(stage)
    errors = gate_errors(project, STAGES[index - 1]) if index > STAGES.index("1.1") else []
    if stage == "1.1":
        errors += (
            material_errors(project)
            + ai_image_config_errors(project)
            + approval_errors(project, "requirements")
        )
    errors += stop_point_errors(project, stage)
    if stage == "1.2":
        errors += content_plan_errors(project)
        errors += generation_jobs_errors(project, "1.2")
        errors += generation_ledger_errors(project, "1.2")
        errors += generation_prompts_errors(project, "1.2")
    if stage == "1.3":
        errors += design_errors(project)
    if stage == "2.1":
        errors += generation_evidence_errors(project, "2.1") + approval_errors(project, "concept")
        errors += generation_prompts_errors(project, "2.1")
    if stage == "2.2":
        errors += generation_evidence_errors(project, "2.2") + approval_errors(project, "preview")
        errors += generation_prompts_errors(project, "2.2")
        errors += deck_style_errors(project)
    errors += stage_preview_errors(project, stage)
    if stage == "3.2":
        manifest = read_json(project / "05_reconstruction/assets.json")
        if not isinstance(manifest, dict) or not isinstance(manifest.get("assets"), list):
            errors.append("重建素材清单必须包含 assets 数组")
    if stage == "3.3":
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "stages/33-build/scripts"))
        from validate_project import validate
        errors += validate(project, mode="release")["errors"]
    if stage == "4":
        content = read_json(project / "02_design/content.json")
        if content.get("include_speaker_script"):
            errors += speaker_script_errors(project)
        # 用户已确认不需要演讲稿：阶段 4 直接跳过并标记完成（交付在 3.3 结束）
    if errors:
        raise ValueError("\n".join(errors))
    state = read_json(project / "workflow-state.json")
    state["version"] = 2
    state["updated_at"] = now()
    skip_speaker = (stage == "4"
                    and not read_json(project / "02_design/content.json").get("include_speaker_script"))
    record = {"status": "complete", "updated_at": now(),
              "files": {} if skip_speaker else collect(project, stage)}
    if skip_speaker:
        record["notes"] = "用户已确认不需要演讲稿：阶段 4 跳过，交付在 3.3 结束。"
    state["stages"][stage] = record
    if stage == "3.3":
        state["pages"] = page_versions(project, read_json(project / "06_build/deck-spec.json"))
    for downstream in STAGES[index + 1:]:
        state["stages"][downstream] = {"status": "not_started", "updated_at": now(), "notes": f"上游阶段 {stage} 已更新，需要重新验收。"}
    write_json(project / "workflow-state.json", state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir")
    commands = parser.add_subparsers(dest="command", required=True)
    register = commands.add_parser("material")
    register.add_argument("--id", required=True)
    register.add_argument("--path", required=True)
    register.add_argument("--kind", choices=["report", "paper", "photo", "promo", "brand", "data", "other"], required=True)
    register.add_argument("--description", default="")
    register.add_argument("--allow-external-upload", action="store_true")
    approve = commands.add_parser("approve")
    approve.add_argument("kind", choices=["requirements", "concept", "preview"])
    approve.add_argument("--evidence", required=True, help="Actual user confirmation quote or message reference")
    approve.add_argument("--option", choices=list("abc"))
    done = commands.add_parser("complete")
    done.add_argument("stage", choices=STAGES[1:])
    wait = commands.add_parser("await")
    wait.add_argument("stage", choices=STAGES[1:])
    wait.add_argument("--notes", required=True)
    commands.add_parser("status")
    commands.add_parser("stop-point", help="报告当前是否可以停在停机点")
    args = parser.parse_args()
    project = Path(args.project_dir).resolve()
    if args.command == "status":
        _status(project)
        return
    if args.command == "stop-point":
        info = stop_point_status(project)
        print(json.dumps(info, ensure_ascii=False, indent=2))
        if not info["canStop"]:
            print(f"错误：{info['reason']}", file=sys.stderr)
            return 1
        return
    with project_lock(project):
        _dispatch(project, args)
    print("完成。批准记录只是用户确认的可追溯记录，不构成用户身份认证。")


def _dispatch(project, args):
    if args.command == "material":
        path = Path(args.path)
        if not path.is_absolute():
            path = project / path
        location = project / "01_inventory/materials.json"
        data = read_json(location) if location.exists() else {"materials": []}
        item = {"id": args.id, "path": portable(project, path), "sha256": digest(path), "kind": args.kind,
                "externalUpload": args.allow_external_upload, "description": args.description}
        data["materials"] = [m for m in data["materials"] if m["id"] != args.id] + [item]
        write_json(location, data)
    elif args.command == "approve":
        if not args.evidence.strip():
            raise ValueError("必须记录真实用户确认，不允许空确认")
        files = ["00_intake/project-brief.md", "01_inventory/materials.json"]
        location = "00_intake/requirements-approval.json"
        record = {"kind": args.kind, "confirmed_at": now(), "evidence": args.evidence}
        if args.kind == "concept":
            if not args.option:
                raise ValueError("方案批准必须指定 --option")
            errors = gate_errors(project, "1.3")
            errors += generation_evidence_errors(project, "2.1")
            errors += stage_preview_errors(project, "2.1") + design_errors(project)
            for option in "abc":
                errors += preview_pages_errors(project, "2.1", option)
            file_errors, generation_files = referenced_generation_files(
                project, "2.1", args.option
            )
            errors += file_errors
            if errors:
                raise ValueError("\n".join(errors))
            record["option"] = args.option
            directory = project / f"03_concepts/option-{args.option}"
            previews = sorted(directory.glob("*.png"))
            if not 1 <= len(previews) <= 3:
                raise ValueError("已选方案必须有 1 至 3 页整页预览 PNG")
            files = ["02_design/design-spec.md", "02_design/content.json", "02_design/claim-map.json",
                     "02_design/generated-assets.json", "02_design/image-intent-plan.json",
                     "03_concepts/concept-review.md",
                     "03_concepts/generation-jobs.json",
                     "03_concepts/generation-ledger.json", "03_concepts/option-"
                     f"{args.option}/preview.json"]
            files += generation_files
            files += [p.relative_to(project).as_posix() for p in previews]
            location = "03_concepts/approval.json"
            (project / "03_concepts/approved-direction.md").write_text(
                f"# 已确认的视觉方向\n\n- 选定方案：{args.option.upper()}\n- 确认记录：{args.evidence}\n- 确认日期：{record['confirmed_at']}\n", encoding="utf-8")
        elif args.kind == "preview":
            errors = gate_errors(project, "2.1")
            errors += deck_style_errors(project)
            errors += stage_preview_errors(project, "2.2")
            errors += preview_pages_errors(project, "2.2")
            file_errors, generation_files = referenced_generation_files(project, "2.2")
            errors += file_errors
            if errors:
                raise ValueError("\n".join(errors))
            files = ["02_design/design-spec.md", "02_design/content.json",
                     "02_design/generated-assets.json", "02_design/image-intent-plan.json",
                     "02_design/image-plan.json", "04_full-preview/previews.json",
                     "04_full-preview/generation-jobs.json", "04_full-preview/generation-ledger.json"]
            files += generation_files
            files += [p.relative_to(project).as_posix() for p in sorted(project.glob("04_full-preview/slides/*.png"))]
            location = "04_full-preview/approval.json"
        record["files"] = {name: digest(project / name) for name in sorted(set(files))}
        write_json(project / location, record)
    elif args.command == "complete":
        complete(project, args.stage)
    elif args.command == "await":
        if args.stage not in STOP_POINTS:
            allowed = "、".join(stop_point_label(stage) for stage in STOP_POINTS)
            raise ValueError(
                f"阶段 {args.stage} 不是停机点：只有 {allowed} 允许暂停等用户；"
                "其他阶段必须连续执行到下一个停机点，不得中途结束任务进程"
            )
        if args.stage == "2.2":
            errors = preview_pages_errors(project, "2.2") + generation_evidence_errors(project, "2.2")
            if errors:
                raise ValueError("完整预览须先插入原图并逐页检查，才可等待批准：\n" + "\n".join(errors))
        state = read_json(project / "workflow-state.json")
        state["updated_at"] = now()
        state["stages"][args.stage] = {
            "status": "awaiting_user",
            "updated_at": now(),
            "notes": args.notes,
            "files": {},
        }
        write_json(project / "workflow-state.json", state)
    else:
        _status(project)


def _status(project):
    state = read_json(project / "workflow-state.json")
    stale = False
    for stage in STAGES[1:]:
        record = state["stages"].get(stage, {})
        if record.get("status") == "complete":
            if stage == "4" and not read_json(project / "02_design/content.json").get("include_speaker_script"):
                continue
            try:
                stale = stale or record.get("files") != collect(project, stage)
            except ValueError:
                stale = True
            if stage == "1.1":
                stale = stale or bool(material_errors(project) + ai_image_config_errors(project))
        print(f"{stage}: {'stale' if stale else record.get('status', 'not_started')}")
    info = stop_point_status(project)
    marker = "可以结束" if info["canStop"] else "必须继续"
    print(f"停机点：{marker}（{info['reason']}）")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        sys.exit(1)
