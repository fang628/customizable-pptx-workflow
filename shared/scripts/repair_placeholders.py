"""Rebuild a derived preview from recorded local blank-frame corrections."""
import argparse
from pathlib import Path

from preview_originals import compose, insert_pages, local_frame_errors, sha
from workflow_lib import project_lock, read_json, schema_errors, write_json


def repair(project, stage, option=None):
    if stage == "2.1" and option not in {"a", "b", "c"}:
        raise ValueError("概念图修框须指定--option a/b/c")
    relative = f"03_concepts/option-{option}/preview.json" if stage == "2.1" else "04_full-preview/previews.json"
    manifest_path = project / relative
    manifest = read_json(manifest_path)
    errors = schema_errors(manifest, "preview-pages")
    if errors:
        raise ValueError("\n".join(errors))
    plans = {s["id"]: s for s in read_json(project / "02_design/image-plan.json")["slides"]}
    ledger_path = "03_concepts/generation-ledger.json" if stage == "2.1" else "04_full-preview/generation-ledger.json"
    ledger = read_json(project / ledger_path)["jobs"]
    updates = []
    for page in manifest["pages"]:
        if not page.get("localPlaceholderRepairs"):
            continue
        record = ledger[page["jobId"]]
        source = project / record["output"]
        if record.get("status") != "complete" or sha(source) != record["sha256"]:
            raise ValueError("本地修框必须基于未改变的真实生成输出")
        page.update(providerFile=record["output"], providerSha256=record["sha256"])
        errors = local_frame_errors(project, page, plans.get(page["id"]))
        if errors:
            raise ValueError("\n".join(errors))
        if stage == "2.1":
            result = compose(project, record["output"], [], page["localPlaceholderRepairs"])
            out = manifest_path.parent / "repairs" / (page["id"] + ".png")
            if out.resolve() == source.resolve():
                raise ValueError("禁止覆盖原始生成输出")
            updates.append((page, out, result))
        page["review"] = ""
    for page, out, result in updates:
        out.parent.mkdir(parents=True, exist_ok=True)
        result.save(out)
        page.update(file=out.relative_to(project).as_posix(), sha256=sha(out))
    write_json(manifest_path, manifest)
    if stage == "2.2":
        insert_pages(project)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--stage", choices=["2.1", "2.2"], required=True)
    parser.add_argument("--option", choices=["a", "b", "c"])
    args = parser.parse_args()
    try:
        with project_lock(args.project):
            repair(args.project, args.stage, args.option)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(1, f"错误：{exc}\n")
    print("已本地修正空白图框；原始生成图与账本保留，请逐页实际查看并重新确认受影响预览。")
