#!/usr/bin/env python3
"""Run provider-neutral image jobs with generous retries; dry-run by default."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared/scripts"))
from imagegen_adapter import call_provider, resolve_script
from preview_images import asset_image_errors, image_errors, normalize, normalize_asset
from workflow_lib import (
    asset_path,
    internal_reference,
    design_errors,
    digest,
    gate_errors,
    generation_jobs_errors,
    generation_paths,
    now,
    preview_prompt_errors,
    project_lock,
    read_json,
    write_json,
)


STAGE_INFO = {
    "concepts": {
        "id": "2.1",
        "folder": "03_concepts",
        "gate": "1.2",
    },
    "full": {
        "id": "2.2",
        "folder": "04_full-preview",
        "gate": "2.1",
    },
    "content": {
        "id": "1.2",
        "folder": "02_design",
        "gate": "1.1",
    },
}


def fingerprint(value):
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _load_config(project):
    try:
        return read_json(project / "00_intake/ai-image-config.json")
    except (OSError, ValueError, TypeError) as exc:
        raise ValueError(f"AI 生图配置不可用：{exc}") from None


def _load_ledger(project, stage, plan, config):
    _, ledger_rel, _ = generation_paths(stage["id"])
    path = project / ledger_rel
    previous = read_json(path) if path.is_file() else {}
    jobs = previous.get("jobs", {}) if isinstance(previous, dict) else {}
    if not isinstance(jobs, dict):
        raise ValueError("现有生图账本的 jobs 必须是对象；请归档后重新生成")
    ledger = {
        "version": 1,
        "provider": config["provider"],
        "model": config["model"],
        "stage": stage["id"],
        "budget": plan.get("max_total_attempts"),
        "attempts": previous.get("attempts", 0) if isinstance(previous, dict) else 0,
        "jobs": jobs,
    }
    if type(ledger["attempts"]) is not int or ledger["attempts"] < 0:
        raise ValueError("现有生图账本的 attempts 无效；请归档后重新生成")
    return path, ledger


def _record_is_traceable(record):
    required = {
        "key",
        "provider",
        "model",
        "request_id",
        "prompt_sha256",
        "adapter_script_sha256",
        "raw_path",
        "raw_sha256",
        "output",
        "sha256",
        "normalization",
    }
    return (
        isinstance(record, dict)
        and record.get("status") == "complete"
        and required.issubset(record)
    )


def _version_key(project, stage, job, reference_hashes, config, script):
    version = {
        "stage": stage["id"],
        "provider": config["provider"],
        "model": config["model"],
        "job": job,
        "references": reference_hashes,
        "adapter_script": digest(script),
        "preview_pipeline": digest(Path(__file__).resolve().parents[3] / "shared/scripts/preview_images.py"),
        "content": digest(project / "02_design/content.json"),
        "design": digest(project / "02_design/design-spec.md"),
        "image_intent": digest(project / "02_design/image-intent-plan.json"),
    }
    if stage["id"] == "2.2":
        version["approval"] = digest(project / "03_concepts/approval.json")
    return fingerprint(version)


def _planned_jobs(project, stage, config, script):
    jobs_rel, _, _ = generation_paths(stage["id"])
    jobs_path = project / jobs_rel
    plan = read_json(jobs_path)
    material_path = project / "01_inventory/materials.json"
    materials = {
        item["id"]: item
        for item in read_json(material_path)["materials"]
    }
    destinations = set()
    planned = []
    for job in plan["jobs"]:
        output = (project / job["output"]).resolve()
        if output in destinations:
            raise ValueError(f"任务输出路径重复：{job['output']}")
        destinations.add(output)
        if job.get("model") and job["model"] != config["model"]:
            raise ValueError(
                f"{job['id']} 的任务模型与配置模型不一致；禁止静默切换模型"
            )
        references = job.get("references", [])
        reference_paths = []
        reference_hashes = {}
        for reference_id in references:
            if internal_reference(project, reference_id):
                path = asset_path(project, reference_id)
            else:
                item = materials.get(reference_id)
                if not item:
                    raise ValueError(f"参考素材未登记：{reference_id}")
                if item.get("externalUpload") is not True:
                    raise ValueError(f"参考素材未获准上传：{reference_id}")
                path = asset_path(project, item["path"])
            with Image.open(path) as image:
                image.verify()
            reference_paths.append(path)
            reference_hashes[reference_id] = digest(path)
        edit_source = job.get("edit_source")
        if isinstance(edit_source, dict):
            edit_path = asset_path(project, edit_source["path"])
            if not edit_path.is_file():
                raise ValueError(f"被编辑素材不存在：{edit_source['path']}")
            with Image.open(edit_path) as image:
                image.verify()
            reference_paths.append(edit_path)
            reference_hashes[f"edit:{edit_source['assetId']}"] = digest(edit_path)
        key = _version_key(
            project,
            stage,
            job,
            reference_hashes,
            config,
            script,
        )
        planned.append(
            {
                "job": job,
                "output": output,
                "references": reference_paths,
                "reference_hashes": reference_hashes,
                "key": key,
            }
        )
    return plan, planned


_FATAL_MARKERS = ("适配脚本", "未配置", "凭据", "不一致", "不存在")


def _fatal(detail):
    """Configuration-level problems are not worth retrying (and cost money)."""
    return any(marker in detail for marker in _FATAL_MARKERS)


def _run_attempt(
    project,
    stage,
    item,
    ledger,
    ledger_path,
    config,
    script,
    python,
    timeout,
    attempt_number,
):
    """Call the provider once. Returns None on success, else a redacted detail."""
    job = item["job"]
    output = item["output"]
    previous = item["previous"]
    key = item["key"]
    jobs_rel, _, _ = generation_paths(stage["id"])
    output_dir = (
        project / Path(jobs_rel).parent / "raw" / job["id"] / key[:12]
    ).resolve()
    ledger["attempts"] += 1
    edit_source = job.get("edit_source")
    record = {
        "key": key,
        "attempts": attempt_number,
        "status": "in_progress",
        "created_at": previous.get("created_at", now()),
        "updated_at": now(),
        "references": job.get("references", []),
    }
    if isinstance(edit_source, dict):
        record["edit_source_asset_id"] = edit_source["assetId"]
        record["edit_source_path"] = edit_source["path"]
        edit_path = asset_path(project, edit_source["path"])
        if edit_path.is_file():
            record["edit_source_sha256"] = digest(edit_path)
    ledger["jobs"][job["id"]] = record
    write_json(ledger_path, ledger)
    try:
        request = {
            "prompt": job["prompt"],
            "size": job.get("size", "1664x928"),
            "output_dir": output_dir,
            "references": item["references"],
        }
        if "seed" in job:
            request["seed"] = job["seed"]
        result = call_provider(
            config,
            request,
            python=python,
            script_override=script,
            timeout=timeout,
        )
        files = result["output_files"]
        if len(files) != 1:
            raise ValueError("输出图数量与任务不一致")
        source = files[0].resolve()
        if not source.is_relative_to(output_dir):
            raise ValueError("生成器返回了输出目录外的文件")
        with Image.open(source) as image:
            image.verify()
        if stage["id"] in {"2.1", "2.2"}:
            conversion = normalize(
                source,
                output,
                job.get("asset_mode", "crop"),
                job.get("asset_background", "#FFFFFF"),
            )
        else:
            conversion = normalize_asset(
                source,
                output,
                job.get("asset_mode", "preserve"),
                job.get("asset_size"),
                job.get("asset_background", "#FFFFFF"),
            )
        record.update(
            {
                "status": "complete",
                "provider": config["provider"],
                "model": result["model"],
                "request_id": result["request_id"],
                "prompt_sha256": hashlib.sha256(job["prompt"].encode("utf-8")).hexdigest(),
                "adapter_script_sha256": digest(result["adapter_script"]),
                "raw_path": source.relative_to(project).as_posix(),
                "raw_sha256": digest(source),
                "output": output.relative_to(project).as_posix(),
                "sha256": digest(output),
                "normalization": conversion,
                "updated_at": now(),
            }
        )
        write_json(ledger_path, ledger)
        return None
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        # Provider diagnostics may contain URLs or credentials; never persist them.
        detail = str(exc)
        lowered = detail.lower()
        if (
            "http://" in lowered
            or "https://" in lowered
            or "bearer " in lowered
            or "api_key" in lowered
            or "token" in lowered
        ):
            detail = "生成失败、输出无效或超时"
        record.update(
            {
                "status": "failed",
                "error": "生成失败、输出无效或超时；原始服务响应未写入日志。",
                "updated_at": now(),
            }
        )
        write_json(ledger_path, ledger)
        return detail


def execute(project, stage_name, script_override, python, run, timeout, attempts=8, job_ids=None):
    stage = STAGE_INFO[stage_name]
    # Missing planned source images stay visible as placeholders in the preview
    # and are rejected by the preview approval gate, not by asset generation.
    errors = gate_errors(
        project,
        stage["gate"],
        verify_materials=False,
        verify_previews=False,
    )
    if stage["id"] == "2.2":
        errors += design_errors(project)
    if errors:
        raise ValueError("\n".join(errors))
    config = _load_config(project)
    configured_script = resolve_script(config)
    script = resolve_script(config, script_override)
    if script.resolve() != configured_script.resolve():
        raise ValueError(
            "命令行生图脚本覆盖与已确认配置不一致；请先更新 "
            "00_intake/ai-image-config.json，不得静默换脚本"
        )
    errors = generation_jobs_errors(project, stage["id"], config)
    if errors:
        raise ValueError("\n".join(errors))
    plan, planned = _planned_jobs(project, stage, config, script)
    if job_ids:
        missing = set(job_ids) - {item["job"]["id"] for item in planned}
        if missing:
            raise ValueError("指定任务不存在：" + "、".join(sorted(missing)))
        planned = [item for item in planned if item["job"]["id"] in job_ids]
    ledger_path, ledger = _load_ledger(project, stage, plan, config)

    for item in planned:
        job = item["job"]
        output = item["output"]
        previous = ledger["jobs"].get(job["id"], {})
        item["previous"] = previous if isinstance(previous, dict) else {}
        item["cached"] = False
        record = item["previous"]
        if (
            record.get("key") == item["key"]
            and _record_is_traceable(record)
            and record.get("output") == job["output"]
            and output.is_file()
            and record.get("sha256") == digest(output)
        ):
            raw = asset_path(project, record["raw_path"])
            item["cached"] = raw.is_file() and digest(raw) == record.get("raw_sha256")
        whole_page = stage["id"] in {"2.1", "2.2"}
        validator = image_errors if whole_page else asset_image_errors
        if item["cached"] and validator(output):
            kind = "1920x1080 整页预览" if whole_page else "独立 AI 素材"
            raise ValueError(f"缓存输出不是有效的{kind}：{output}")
        if not item["cached"] and output.exists():
            if record.get("key") != item["key"]:
                raise ValueError(
                    f"{job['id']} 已有不同版本的输出；请归档旧图并指定新的输出位置"
                )
            if record.get("status") == "complete" and record.get("sha256") != digest(output):
                raise ValueError(
                    f"{job['id']} 的输出已被后处理或手工修改；"
                    "停止覆盖并保留原始生成图"
                )
        used = record.get("attempts", 0) if record.get("key") == item["key"] else 0
        item["used"] = used

    if stage["id"] in {"2.1", "2.2"}:
        # Inspect every request that will be sent, including a changed cached prompt.
        # Preserve traceable historical parents used by image edits without resending them.
        pending_ids = {item["job"]["id"] for item in planned if not item["cached"]}
        errors = preview_prompt_errors(project, stage["id"], job_ids=pending_ids) if pending_ids else []
        if errors:
            raise ValueError("\n".join(errors))
    summary = {
        "stage": stage["id"],
        "provider": config["provider"],
        "model": config["model"],
        "adapter_script": str(script),
        "execute": run,
        "attempts_used": ledger["attempts"],
        "attempt_limit_per_job": attempts,
        "budget": None,
        "jobs": [
            {
                "id": item["job"]["id"],
                "cached": item["cached"],
                "attempts": item["used"],
                "attempt_limit": int(item["job"].get("max_attempts", attempts)),
            }
            for item in planned
        ],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not run:
        return

    failures = []
    for item in planned:
        job = item["job"]
        if item["cached"]:
            continue
        limit = int(job.get("max_attempts", attempts))
        base = int(item["used"])
        detail = None
        for index in range(1, limit + 1):
            detail = _run_attempt(
                project,
                stage,
                item,
                ledger,
                ledger_path,
                config,
                script,
                python,
                timeout,
                base + index,
            )
            if detail is None:
                break
            print(
                f"提示：{job['id']} 第 {index}/{limit} 次尝试失败：{detail}",
                file=sys.stderr,
            )
            if _fatal(detail):
                print(
                    f"提示：{job['id']} 属于配置类问题，停止重试以免继续计费",
                    file=sys.stderr,
                )
                break
        if detail is not None:
            failures.append(f"{job['id']}：{detail}")
    if failures:
        raise ValueError(
            "以下任务在本轮尝试后仍未成功："
            + "；".join(failures)
            + f"；生图不设次数预算，可再次运行继续重试（单任务本轮上限 {attempts} 次，"
            "用 --attempts 调整）"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir")
    parser.add_argument(
        "--stage", choices=["content", "concepts", "full"], required=True
    )
    scripts = parser.add_mutually_exclusive_group()
    scripts.add_argument(
        "--adapter-script",
        help="Provider-neutral script override; must match the approved config.",
    )
    scripts.add_argument(
        "--qwen-script",
        help="Legacy alias for --adapter-script.",
    )
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--job", action="append", help="只运行指定任务，可重复；保留清单中的历史图生图来源")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument(
        "--attempts",
        type=int,
        default=8,
        help="单任务在本轮运行内的最大尝试次数；不是次数预算，可按需要调大",
    )
    args = parser.parse_args()
    try:
        if args.timeout < 1:
            raise ValueError("timeout 必须为正整数")
        if args.attempts < 1:
            raise ValueError("--attempts 必须为正整数")
        project = Path(args.project_dir).resolve()
        with project_lock(project):
            execute(
                project,
                args.stage,
                args.adapter_script or args.qwen_script,
                args.python,
                args.execute,
                args.timeout,
                args.attempts,
                args.job,
            )
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        sys.exit(1)
