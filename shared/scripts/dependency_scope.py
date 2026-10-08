"""Conservative page-scoped dependencies for recovery, approvals and image caches.

Unknown Markdown/metadata remains global. Legacy records keep strict file hashes.
This module never updates an approval or marks a pending page as reviewed.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

SCOPED_STAGES = ("1.3", "2.1", "2.2", "3.1", "3.2", "3.3", "4")
PAGE = re.compile(r"\bS\d{2,}\b")


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def load(project, relative, default=None):
    path = Path(relative)
    if not path.is_absolute():
        path = project / path
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def file_hash(project, relative):
    path = Path(relative)
    if not path.is_absolute():
        path = project / path
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def markdown_parts(text):
    """Split explicit page sections/table rows; unclassified prose stays global."""
    shared, pages = [], {}
    current, level, fence = None, 0, None
    for line in text.splitlines():
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            fence = marker[1][0] if fence is None else None if marker[1][0] == fence else fence
        heading = re.match(r"^(#{1,6})\s+(.*)", line) if fence is None and not marker else None
        if heading:
            page_heading = re.match(r"(S\d{2,})(?:\s|[：:—-]|$)", heading[2])
            if page_heading:
                current, level = page_heading[1], len(heading[1])
            elif current and len(heading[1]) <= level:
                current = None
        ids = set(PAGE.findall(line)) if fence is None and line.lstrip().startswith("|") else set()
        if current:
            pages.setdefault(current, []).append(line)
        elif ids:
            for identifier in ids:
                pages.setdefault(identifier, []).append(line)
        elif line.strip():
            shared.append(line)
    return "\n".join(shared), {k: "\n".join(v) for k, v in pages.items()}


def _split_document(project, path, shared, pages, identifiers):
    text = (project / path).read_text(encoding="utf-8-sig")
    common, fragments = markdown_parts(text)
    shared[path] = common
    for identifier in identifiers:
        pages[identifier][path] = fragments.get(identifier)


def snapshot(project, stage, page_ids=None, include_outputs=True, option=None):
    """Snapshot semantic page inputs plus actual referenced file bytes."""
    from workflow_lib import ARTIFACTS
    project = Path(project)
    if stage not in SCOPED_STAGES:
        inputs = ["00_intake/project-brief.md", "00_intake/ai-image-config.json",
                  "01_inventory/materials.json"]
        if stage == "1.2":
            materials = load(project, "01_inventory/materials.json", {}).get("materials", [])
            inputs += [item["path"] for item in materials]
        if include_outputs:
            for pattern in ARTIFACTS.get(stage, []):
                inputs += [p.relative_to(project).as_posix() for p in project.glob(pattern) if p.is_file()]
        return {"version": 1, "shared": fingerprint({p: file_hash(project, p) for p in inputs}), "pages": {}}
    content = load(project, "02_design/content.json", {})
    slides = {s["id"]: s for s in content.get("slides", [])}
    manifests = []
    if stage == "2.1":
        options = [option] if option else list("abc")
        for direction in options:
            relative = f"03_concepts/option-{direction}/preview.json"
            manifest = load(project, relative, {})
            manifests.append((relative, manifest))
        ids = {p["id"] for _, m in manifests for p in m.get("pages", [])}
    else:
        ids = set(slides)
    if page_ids is not None:
        ids = set(page_ids)
    pages = {identifier: {} for identifier in sorted(ids)}
    shared = {p: file_hash(project, p) for p in
              ("00_intake/project-brief.md", "00_intake/ai-image-config.json")}
    shared["content"] = {k: v for k, v in content.items() if k != "slides"}
    # Ordering matters globally, including pages not used in concept comparisons.
    shared["order"] = list(slides)
    for identifier in pages:
        pages[identifier]["content"] = slides.get(identifier)
    paths = ["02_design/design-spec.md", "02_design/claim-map.json", "02_design/image-intent-plan.json"]
    if stage not in {"1.3", "2.1"}:
        paths.append("02_design/image-plan.json")
    for relative in paths:
        path = project / relative
        if not path.is_file():
            shared[relative] = None
        elif path.suffix == ".md":
            _split_document(project, relative, shared, pages, ids)
        else:
            data = load(project, relative)
            shared[relative] = {k: v for k, v in data.items() if k != "slides"}
            rows = {s["id"]: s for s in data.get("slides", [])}
            for identifier in pages:
                pages[identifier][relative] = rows.get(identifier)
    # Project each source registry by actual use rather than hashing the whole list.
    registries = []
    for relative, key in (("01_inventory/materials.json", "materials"),
                          ("02_design/generated-assets.json", "assets")):
        registries.extend(load(project, relative, {}).get(key, []))
    for identifier, values in pages.items():
        serialized = json.dumps(values, ensure_ascii=False)
        used = [r for r in registries if r.get("id") and r["id"] in serialized]
        values["sources"] = [{"record": r, "actual": file_hash(project, r["path"])}
                             for r in used if r.get("path")]
    if stage not in {"1.3", "2.1"}:
        relative = "04_full-preview/previews.json"
        manifests = [(relative, load(project, relative, {}))]
        shared["direction"] = load(project, "03_concepts/approval.json", {}).get("option")
    if include_outputs or stage in {"3.1", "3.2", "3.3", "4"}:
        for relative, manifest in manifests:
            shared[relative] = {k: v for k, v in manifest.items() if k != "pages"}
            folder = "03_concepts" if stage == "2.1" else "04_full-preview"
            jobs = load(project, f"{folder}/generation-jobs.json", {}).get("jobs", [])
            ledger = load(project, f"{folder}/generation-ledger.json", {}).get("jobs", {})
            for page in manifest.get("pages", []):
                identifier = page["id"]
                if identifier not in pages:
                    continue
                job_id = page.get("jobId")
                values = pages[identifier]
                values[relative] = page
                values[f"{relative}:jobs"] = [j for j in jobs if j.get("id") == job_id]
                record = ledger.get(job_id, {})
                values[f"{relative}:ledger"] = record
                files = [page.get("file"), page.get("providerFile")]
                files += [record.get(k) for k in ("raw_path", "output", "tool_receipt_path")]
                files += [o.get("path") for o in page.get("originals", [])]
                # Reference/edit source changes also invalidate the page.
                for job in values[f"{relative}:jobs"]:
                    for ref in job.get("references", []):
                        registered = next((r for r in registries if r.get("id") == ref), {})
                        files.append(registered.get("path", ref))
                    files.append(job.get("edit_source", {}).get("path"))
                values[f"{relative}:files"] = {p: file_hash(project, p) for p in files if p}
    if stage in {"3.2", "3.3", "4"}:
        for relative in ("05_reconstruction/element-inventory.md", "05_reconstruction/slide-elements.md"):
            if (project / relative).is_file():
                _split_document(project, relative, shared, pages, ids)
        if stage in {"3.3", "4"} or include_outputs:
            assets = load(project, "05_reconstruction/assets.json", {}).get("assets", [])
            deck = load(project, "06_build/deck-spec.json", {})
            deck_rows = {s["id"]: s for s in deck.get("slides", [])}
            for identifier, values in pages.items():
                row = deck_rows.get(identifier, {})
                refs = json.dumps(row if stage in {"3.3", "4"} else values, ensure_ascii=False)
                used = [a for a in assets if any(a.get(k) and a[k] in refs for k in ("sourceId", "path"))]
                values["reconstruction"] = [{"record": a, "actual": file_hash(project, a["path"])} for a in used]
                if stage in {"3.3", "4"}:
                    values["deck"] = row
                    values["deck_files"] = {e["path"]: file_hash(project, e["path"])
                                            for e in row.get("elements", []) if e.get("path")}
            if stage in {"3.3", "4"}:
                shared["deck"] = {k: v for k, v in deck.items() if k != "slides"}
    return {"version": 1, "shared": fingerprint(shared),
            "pages": {identifier: fingerprint(values) for identifier, values in pages.items()}}


def difference(before, after):
    if not before or before.get("version") != 1:
        return {"global": True, "pages": sorted(after.get("pages", {})), "reason": "旧记录缺少依赖快照，须重新验收"}
    identifiers = set(before["pages"]) | set(after["pages"])
    global_change = before["shared"] != after["shared"]
    changed = sorted(identifiers if global_change else
                     (p for p in identifiers if before["pages"].get(p) != after["pages"].get(p)))
    return {"global": global_change, "pages": changed,
            "reason": "全篇依赖改变" if global_change else "页面或所用素材改变"}


def scoped_approval_errors(project, approval):
    stage = "2.1" if approval["kind"] == "concept" else "2.2"
    current = snapshot(project, stage, option=approval.get("option"))
    change = difference(approval.get("scope"), current)
    errors = []
    if change["global"]:
        errors.append(f"{approval['kind']} 批准的全篇依赖已变化，需要重新确认")
    if change["pages"]:
        errors.append(f"{approval['kind']} 批准已失效的页面：" + "、".join(change["pages"]))
    confirmations = approval.get("page_confirmations", {})
    for identifier, value in current["pages"].items():
        record = confirmations.get(identifier, {})
        if record.get("sha256") != value or not record.get("evidence") or not record.get("confirmed_at"):
            errors.append(f"{identifier} 缺少与当前页面依赖绑定的真实确认记录")
    return errors


def review_dependencies(project):
    scope = snapshot(Path(project), "3.3", include_outputs=False)
    return {identifier: fingerprint({"shared": scope["shared"], "page": value})
            for identifier, value in scope["pages"].items()}
