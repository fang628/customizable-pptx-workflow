"""Import real built-in image_gen results; this module never generates images."""

from __future__ import annotations

import hashlib
from pathlib import Path
import shutil

from PIL import Image


def receipt_errors(project, job, record):
    from workflow_lib import asset_path, digest, read_json

    errors = []
    receipt = asset_path(project, record.get("tool_receipt_path", ""))
    if (not receipt.resolve().is_relative_to(project.resolve())
            or "raw" not in receipt.parts or not receipt.is_file()):
        return [f"{job['id']} 缺少项目raw目录中的内置工具调用回执"]
    if digest(receipt) != record.get("tool_receipt_sha256"):
        errors.append(f"{job['id']} 的内置工具回执哈希已变化")
    try:
        evidence = read_json(receipt)
        expected = {
            "job_id": job["id"], "tool_call_id": record.get("tool_call_id"),
            "prompt_sha256": record.get("prompt_sha256"),
            "raw_sha256": record.get("raw_sha256"),
            "tool": "image_gen", "tool_result_id": record.get("tool_result_id"), "reference_sha256": {},
        }
        materials = {m["id"]: m for m in read_json(project / "01_inventory/materials.json")["materials"]}
        for reference in job.get("references", []):
            path = materials[reference]["path"] if reference in materials else reference
            expected["reference_sha256"][reference] = digest(asset_path(project, path))
        source = job.get("edit_source")
        if source:
            expected["reference_sha256"][f"edit:{source['assetId']}"] = digest(asset_path(project, source["path"]))
        for key, value in expected.items():
            if evidence.get(key) != value:
                errors.append(f"{job['id']} 的内置工具回执与当前 {key} 不一致")
        if evidence.get("tool_model") != record.get("tool_model"):
            errors.append(f"{job['id']} 的工具模型披露与回执不一致")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        errors.append(f"{job['id']} 无法验证内置工具回执：{type(exc).__name__}")
    return errors


def import_result(project, stage, planned, ledger, ledger_path, config, script, receipt_path):
    from preview_images import normalize, normalize_asset
    from workflow_lib import digest, now, read_json, write_json

    evidence = read_json(Path(receipt_path))
    if not isinstance(evidence, dict) or evidence.get("tool") != "image_gen":
        raise ValueError("回执必须来自真实 image_gen 工具调用；不接受CLI或本地绘图结果")
    items = [item for item in planned if item["job"]["id"] == evidence.get("job_id")]
    if len(items) != 1:
        raise ValueError("回执任务必须属于当前阶段与所选任务")
    item = items[0]
    job = item["job"]
    call_id = evidence.get("tool_call_id")
    if call_id is not None and (not isinstance(call_id, str) or not call_id.strip()):
        raise ValueError("调用编号仅在工具真实披露时记录，不得编造")
    prompt_hash = hashlib.sha256(job["prompt"].encode("utf-8")).hexdigest()
    if evidence.get("prompt_sha256") != prompt_hash:
        raise ValueError("实际调用提示词哈希与当前任务不一致")
    if evidence.get("reference_sha256") != item["reference_hashes"]:
        raise ValueError("实际调用参考图／编辑源哈希与当前任务不一致")
    source = Path(evidence["source_file"]).expanduser().resolve()
    if evidence.get("tool_result_id") != source.name:
        raise ValueError("工具结果标识须为真实返回文件名，不得编造调用编号")
    with Image.open(source) as image:
        image.verify()
    if evidence.get("raw_sha256") != digest(source):
        raise ValueError("工具返回原图哈希与回执不一致")
    output = item["output"]
    if output.exists():
        raise ValueError("输出已存在；内置工具结果不得覆盖，修订须新任务、新GEN编号")
    if any((call_id and r.get("tool_call_id") == call_id) or (r.get("tool_result_id") == source.name and r.get("raw_sha256") == digest(source)) for r in ledger["jobs"].values()):
        raise ValueError("工具调用编号已经登记，不得重复用作另一张图的生成证据")
    previous = item.get("previous", {})
    attempts = int(previous.get("attempts", 0)) + 1
    if attempts > job.get("max_attempts", 8):
        raise ValueError("达到单任务尝试上限；先按实际需要更新max_attempts再继续")
    folder = ledger_path.parent / "raw" / job["id"] / item["key"][:12] / str(attempts)
    folder.mkdir(parents=True, exist_ok=False)
    raw = folder / ("tool-output" + source.suffix.lower())
    shutil.copy2(source, raw)
    saved = {k: evidence[k] for k in ("tool", "job_id", "tool_result_id", "prompt_sha256", "reference_sha256", "raw_sha256")}
    if call_id:
        saved["tool_call_id"] = call_id
    if evidence.get("tool_model"):
        saved["tool_model"] = evidence["tool_model"]
    receipt = folder / "tool-receipt.json"
    write_json(receipt, saved)
    with Image.open(raw) as image:
        size = list(image.size)
    record = {
        "key": item["key"], "attempts": attempts, "status": "in_progress",
        "created_at": previous.get("created_at", now()), "updated_at": now(),
        "provider": "imagegen", "model": config["model"], "tool_result_id": source.name,
        "tool_receipt_path": receipt.relative_to(project).as_posix(),
        "tool_receipt_sha256": digest(receipt), "prompt_sha256": prompt_hash,
        "adapter_script_sha256": digest(script), "references": job.get("references", []),
        "raw_path": raw.relative_to(project).as_posix(), "raw_sha256": digest(raw),
        "original_size": size, "output": job["output"],
    }
    if call_id:
        record["tool_call_id"] = call_id
    if evidence.get("tool_model"):
        record["tool_model"] = evidence["tool_model"]
    if job.get("edit_source"):
        src = job["edit_source"]
        record.update(edit_source_asset_id=src["assetId"], edit_source_path=src["path"],
                      edit_source_sha256=item["reference_hashes"][f"edit:{src['assetId']}"])
    ledger["attempts"] += 1
    ledger["jobs"][job["id"]] = record
    write_json(ledger_path, ledger)
    try:
        if stage["id"] in {"2.1", "2.2"}:
            record["normalization"] = normalize(raw, output, "strict", job.get("asset_background", "#FFFFFF"))
        else:
            record["normalization"] = normalize_asset(raw, output, job.get("asset_mode", "preserve"),
                                                       job.get("asset_size"), job.get("asset_background", "#FFFFFF"))
        record.update(status="complete", sha256=digest(output), updated_at=now())
    except (OSError, ValueError):
        record.update(status="failed", error="工具输出尺寸或图片不合格，保留原图与回执后退回修订", updated_at=now())
        write_json(ledger_path, ledger)
        raise
    write_json(ledger_path, ledger)
