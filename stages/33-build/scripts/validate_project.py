#!/usr/bin/env python3
"""Validate specification, OOXML relationships, provenance and release gates."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import hashlib
from pathlib import Path
import posixpath
import sys
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared/scripts"))
from workflow_lib import canvas, check_hashes, digest, gate_errors, read_json, schema_errors, speaker_script_errors, spec_errors, write_json
from preview_images import image_errors

P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
REVIEW_CHECKS = ("visual", "content", "photos", "editability")


def inspect_pptx(path, spec):
    errors, audit = [], []
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            errors.append("PPTX 包含重复成员名")
        if archive.testzip():
            errors.append("PPTX ZIP 校验失败")
        required = {"[Content_Types].xml", "_rels/.rels", "ppt/presentation.xml", "ppt/_rels/presentation.xml.rels"}
        if not required.issubset(names):
            return [f"缺少 OOXML 成员：{sorted(required - set(names))}"], []
        xml = {}
        for name in names:
            if name.endswith((".xml", ".rels")):
                try:
                    xml[name] = ET.fromstring(archive.read(name))
                except ET.ParseError:
                    errors.append(f"无效 XML：{name}")
        if errors:
            return errors, []
        if xml["[Content_Types].xml"].tag != f"{{{CT}}}Types" or xml["ppt/presentation.xml"].tag != f"{{{P}}}presentation":
            return ["OOXML 根元素或命名空间错误"], []
        relationships = {}
        for name, root in xml.items():
            if not name.endswith(".rels"):
                continue
            if root.tag != f"{{{REL}}}Relationships":
                errors.append(f"关系文件根节点错误：{name}")
                continue
            base = posixpath.dirname(posixpath.dirname(name)) if name != "_rels/.rels" else ""
            mapping = {}
            for relation in root:
                rid = relation.get("Id")
                if not rid or rid in mapping:
                    errors.append(f"重复或缺失关系 ID：{name}")
                target = relation.get("Target", "")
                external = relation.get("TargetMode") == "External"
                resolved = posixpath.normpath(posixpath.join(base, target)) if not target.startswith("/") else target.lstrip("/")
                mapping[rid] = (resolved, relation.get("Type", ""), external)
                if not external and (resolved.startswith("../") or resolved not in names):
                    errors.append(f"关系目标缺失：{name} -> {target}")
            relationships[name] = mapping
        if not any(t.endswith("/officeDocument") and target == "ppt/presentation.xml" and not external
                   for target, t, external in relationships.get("_rels/.rels", {}).values()):
            errors.append("缺少根 officeDocument 关系")
        types = xml["[Content_Types].xml"]
        overrides = {e.get("PartName", "").lstrip("/"): e.get("ContentType", "") for e in types if e.tag.endswith("}Override")}
        defaults = {e.get("Extension"): e.get("ContentType") for e in types if e.tag.endswith("}Default")}
        for name in names:
            if name.endswith("/") or name == "[Content_Types].xml":
                continue
            if name not in overrides and name.rsplit(".", 1)[-1] not in defaults:
                errors.append(f"成员未声明内容类型：{name}")
        presentation = xml["ppt/presentation.xml"]
        slide_ids = presentation.findall(f"{{{P}}}sldIdLst/{{{P}}}sldId")
        if not slide_ids or len(slide_ids) != len(spec["slides"]):
            errors.append(f"页数不一致：spec={len(spec['slides'])}, pptx={len(slide_ids)}")
        width, height = canvas(spec)
        size = presentation.find(f"{{{P}}}sldSz")
        if size is None or abs(int(size.get("cx", 0)) / 914400 - width) > .01 or abs(int(size.get("cy", 0)) / 914400 - height) > .01:
            errors.append("PPTX 画布与规格不一致")
        rels = relationships.get("ppt/_rels/presentation.xml.rels", {})
        targets = set()
        for index, slide_id in enumerate(slide_ids):
            target, relation_type, external = rels.get(slide_id.get(f"{{{R}}}id"), ("", "", False))
            if external or not relation_type.endswith("/slide") or target not in xml or target in targets:
                errors.append(f"第 {index + 1} 页关系无效或重复")
                continue
            targets.add(target)
            slide = xml[target]
            if slide.tag != f"{{{P}}}sld" or not overrides.get(target, "").endswith("presentationml.slide+xml"):
                errors.append(f"页面 XML 或内容类型错误：{target}")
            for element in slide.iter():
                for attr, rid in element.attrib.items():
                    if attr in {f"{{{R}}}id", f"{{{R}}}embed", f"{{{R}}}link"}:
                        slide_rel = posixpath.join(posixpath.dirname(target), "_rels", posixpath.basename(target) + ".rels")
                        if rid not in relationships.get(slide_rel, {}):
                            errors.append(f"页面关系引用缺失：{target} -> {rid}")
            text_shapes = []
            for shape in slide.findall(f".//{{{P}}}sp"):
                paragraphs = shape.findall(f"{{{P}}}txBody/{{{A}}}p")
                if paragraphs:
                    lines = []
                    for paragraph in paragraphs:
                        lines.append("".join("\n" if node.tag == f"{{{A}}}br" else node.text or ""
                                             for node in paragraph.iter() if node.tag in {f"{{{A}}}t", f"{{{A}}}br"}))
                    text_shapes.append("\n".join(lines))
            expected_slide = spec["slides"][index] if index < len(spec["slides"]) else None
            if expected_slide:
                expected = Counter(e["text"].replace("\r\n", "\n") for e in expected_slide["elements"] if e["type"] == "text")
                if expected != Counter(text_shapes):
                    errors.append(f"第 {index + 1} 页原生文本与规格不一致")
                counts = Counter(e["type"] for e in expected_slide["elements"])
                if len(slide.findall(f".//{{{P}}}pic")) != counts["image"] + counts["svg"]:
                    errors.append(f"第 {index + 1} 页独立图片数量不一致")
                if len(slide.findall(f".//{{{A}}}tbl")) != counts["table"]:
                    errors.append(f"第 {index + 1} 页原生表格数量不一致")
                chart_ns = "http://schemas.openxmlformats.org/drawingml/2006/chart"
                if len(slide.findall(f".//{{{chart_ns}}}chart")) != counts["chart"]:
                    errors.append(f"第 {index + 1} 页原生图表数量不一致")
                object_names = [e.get("name") for e in slide.findall(f".//{{{P}}}cNvPr")]
                for element in expected_slide["elements"]:
                    if object_names.count(element["id"]) != 1:
                        errors.append(f"对象编号缺失或重复：{element['id']}")
                    if element["type"] not in {"table", "chart"}:
                        continue
                    frames = [frame for frame in slide.findall(f".//{{{P}}}graphicFrame")
                              if any(prop.get("name") == element["id"] for prop in frame.findall(f".//{{{P}}}cNvPr"))]
                    if len(frames) != 1:
                        errors.append(f"原生数据对象缺失：{element['id']}")
                        continue
                    if element["type"] == "table":
                        rows = frames[0].findall(f".//{{{A}}}tbl/{{{A}}}tr")
                        actual = [["\n".join("".join(t.text or "" for t in paragraph.iter(f"{{{A}}}t"))
                                             for paragraph in cell.findall(f"{{{A}}}txBody/{{{A}}}p"))
                                   for cell in row.findall(f"{{{A}}}tc")] for row in rows]
                        expected = [[str(cell.get("text", "") if isinstance(cell, dict) else cell) for cell in row] for row in element["rows"]]
                        if actual != expected:
                            errors.append(f"原生表格内容不一致：{element['id']}")
                    else:
                        chart_node = frames[0].find(f".//{{{chart_ns}}}chart")
                        slide_rel = posixpath.join(posixpath.dirname(target), "_rels", posixpath.basename(target) + ".rels")
                        chart_target = relationships.get(slide_rel, {}).get(chart_node.get(f"{{{R}}}id"), ("", "", False))[0] if chart_node is not None else ""
                        chart_root = xml.get(chart_target)
                        if chart_root is None:
                            errors.append(f"图表数据文件缺失：{element['id']}")
                            continue
                        series = chart_root.findall(f".//{{{chart_ns}}}ser")
                        if len(series) != len(element["data"]):
                            errors.append(f"图表系列数量不一致：{element['id']}")
                        for actual_series, expected_series in zip(series, element["data"]):
                            values = actual_series.find(f"{{{chart_ns}}}val")
                            if values is None:
                                values = actual_series.find(f"{{{chart_ns}}}yVal")
                            actual_values = [] if values is None else [float(v.text) for v in values.findall(f".//{{{chart_ns}}}pt/{{{chart_ns}}}v")]
                            if actual_values != expected_series["values"]:
                                errors.append(f"图表缓存数值不一致：{element['id']}")
            audit.append({"slide": index + 1, "part": target, "native_texts": len(text_shapes), "pictures": len(slide.findall(f".//{{{P}}}pic"))})
    return errors, audit


def _load_json(project, relative, errors):
    path = project / relative
    if not path.is_file() or not path.stat().st_size:
        errors.append(f"缺少阶段 3.3 产物：{relative}")
        return None
    try:
        return read_json(path)
    except (OSError, ValueError, TypeError) as exc:
        errors.append(f"无法读取 {relative}：{exc}")
        return None


def _load_artifact(project, relative, schema_name, errors):
    value = _load_json(project, relative, errors)
    if value is None:
        return None
    errors.extend(schema_errors(value, schema_name))
    return value


def _check_hash(project, relative, expected, errors, label):
    path = project / relative
    if not path.is_file():
        errors.append(f"{label} 文件缺失：{relative}")
        return False
    if digest(path) != expected:
        errors.append(f"{label} 与记录不一致：{relative}")
        return False
    return True


def _manifest_pages(manifest, expected_ids, label, errors):
    pages = manifest.get("pages", []) if isinstance(manifest, dict) else []
    if [page.get("id") for page in pages] != expected_ids:
        errors.append(f"{label}页面编号或顺序不完整")
        return {}
    return {page["id"]: page for page in pages}


def _approved_deviation(page):
    deviations = page.get("deviations")
    if not isinstance(deviations, list) or not deviations:
        return False
    return all(
        isinstance(item, dict)
        and item.get("approved_by")
        and item.get("approved_at")
        for item in deviations
    )


def _validate_review_manifest(project, render, expected_ids, errors):
    relative = "07_delivery/review-manifest.json"
    manifest = _load_artifact(project, relative, "review-manifest", errors)
    if not isinstance(manifest, dict):
        return None
    if not _check_hash(project, "07_delivery/deck.pptx", manifest.get("pptx_sha256"), errors, "审阅清单 PPTX"):
        pass
    if manifest.get("image_plan_sha256") != digest(project / "02_design/image-plan.json"):
        errors.append("审阅清单不是当前图片计划版本")
    if manifest.get("previews_sha256") != digest(project / "04_full-preview/previews.json"):
        errors.append("审阅清单不是当前整页预览版本")
    if manifest.get("preview_approval_sha256") != digest(project / "04_full-preview/approval.json"):
        errors.append("审阅清单不是当前预览批准版本")
    if manifest.get("render_manifest_sha256") != digest(project / "07_delivery/render-manifest.json"):
        errors.append("审阅清单不是当前渲染版本")
    pages = _manifest_pages(manifest, expected_ids, "审阅清单", errors)
    render_pages = _manifest_pages(render, expected_ids, "渲染", errors)
    for page_id in expected_ids:
        page = pages.get(page_id)
        if not page:
            continue
        preview_path = project / page.get("preview_path", "")
        expected_preview = f"04_full-preview/slides/{page_id}.png"
        if page.get("preview_path") != expected_preview or not preview_path.is_file():
            errors.append(f"审阅清单源预览路径无效：{page_id}")
        elif digest(preview_path) != page.get("preview_sha256"):
            errors.append(f"审阅清单源预览已变化：{page_id}")
        if page.get("render_path") != render_pages.get(page_id, {}).get("path"):
            errors.append(f"审阅清单渲染路径与渲染清单不一致：{page_id}")
        if page.get("render_sha256") != render_pages.get(page_id, {}).get("sha256"):
            errors.append(f"审阅清单渲染哈希与渲染清单不一致：{page_id}")
        compare_path = project / page.get("compare_path", "")
        if not compare_path.is_file():
            errors.append(f"审阅清单对照图缺失：{page_id}")
    return manifest


def _validate_qa_review(project, render, expected_ids, errors):
    relative = "07_delivery/qa-review.json"
    review = _load_artifact(project, relative, "qa-review", errors)
    if not isinstance(review, dict):
        return
    expected_hashes = {
        "content_sha256": digest(project / "02_design/content.json"),
        "image_plan_sha256": digest(project / "02_design/image-plan.json"),
        "previews_sha256": digest(project / "04_full-preview/previews.json"),
        "pptx_package_sha256": digest(project / "07_delivery/deck.pptx"),
        "render_manifest_sha256": digest(project / "07_delivery/render-manifest.json"),
    }
    for key, expected in expected_hashes.items():
        if review.get(key) != expected:
            errors.append(f"人工审阅绑定版本已失效：{key}")
    if not review.get("reviewer") or not review.get("reviewed_at"):
        errors.append("缺少审阅人或审阅时间")

    pages = _manifest_pages(review, expected_ids, "人工审阅", errors)
    render_pages = _manifest_pages(render, expected_ids, "渲染", errors)
    from dependency_scope import review_dependencies
    dependencies = review_dependencies(project)
    for page_id in expected_ids:
        page = pages.get(page_id)
        if not page:
            continue
        if page.get("render_sha256") != render_pages.get(page_id, {}).get("sha256"):
            errors.append(f"逐页人工审阅不属于当前渲染版本：{page_id}")
        if page.get("dependency_sha256") and page["dependency_sha256"] != dependencies.get(page_id):
            errors.append(f"逐页人工审阅的内容、素材或构建依赖已失效：{page_id}")
        if page.get("review_mode") not in {"manual", "assisted"} or page.get("human_signed") is not True:
            errors.append(f"逐页人工审阅尚未由人员签署：{page_id}")
        for check in REVIEW_CHECKS:
            if page.get(check) is not True:
                errors.append(f"逐页人工审阅未通过 {check}：{page_id}")
        if page.get("preview_match") is not True and not _approved_deviation(page):
            errors.append(f"逐页人工审阅未通过 preview_match 且没有已批准偏差：{page_id}")
    report = project / "07_delivery/qa-report.md"
    if not report.is_file() or not report.stat().st_size:
        errors.append("缺少面向用户的质量检查报告")


def validate(project, mode="draft", spec_only=False):
    errors, audit = [], []
    try:
        spec = read_json(project / "06_build/deck-spec.json")
        errors += spec_errors(project, spec, release=mode == "release")
        if mode == "release":
            errors += gate_errors(project)
            content_path = project / "02_design/content.json"
            if content_path.is_file():
                try:
                    content = read_json(content_path)
                except (OSError, ValueError, TypeError):
                    content = {}
                if content.get("include_speaker_script"):
                    errors += speaker_script_errors(project)
        if not errors and not spec_only:
            pptx = project / "07_delivery/deck.pptx"
            found, audit = inspect_pptx(pptx, spec)
            errors += found
            if mode == "release":
                image_plan = read_json(project / "02_design/image-plan.json")
                expected_ids = [slide["id"] for slide in spec["slides"]]
                manifest = _load_json(project, "07_delivery/build-manifest.json", errors)
                if not isinstance(manifest, dict) or manifest.get("mode") != "release":
                    errors.append("试构建不能作为正式交付；请以 --mode release 重建")
                else:
                    errors += check_hashes(project, manifest.get("inputs"))
                    if manifest.get("pptx_sha256") != digest(pptx):
                        errors.append("PPTX 与构建记录不一致")
                    with zipfile.ZipFile(pptx) as archive:
                        embedded = {
                            hashlib.sha256(archive.read(name)).hexdigest()
                            for name in archive.namelist()
                            if name.startswith("ppt/media/")
                        }
                    expected_images = {
                        element["id"]
                        for slide in spec["slides"]
                        for element in slide["elements"]
                        if element["type"] == "image"
                    }
                    recorded_images = {asset.get("id") for asset in manifest.get("assets", [])}
                    if expected_images != recorded_images:
                        errors.append("图片嵌入记录不完整")
                    for asset in manifest.get("assets", []):
                        if asset.get("embedded_sha256") not in embedded:
                            errors.append(f"图片嵌入字节与记录不一致：{asset.get('id')}")

                render_path = project / "07_delivery/render-manifest.json"
                render = _load_artifact(project, "07_delivery/render-manifest.json", "render", errors)
                if isinstance(render, dict):
                    if render.get("pptx_sha256") != digest(pptx):
                        errors.append("渲染图不是当前 PPTX 版本")
                    width, height = render.get("width", 0), render.get("height", 0)
                    if width <= 0 or width % 16 or width * 9 != height * 16:
                        errors.append("渲染画布不是严格 16:9")
                    pages = _manifest_pages(render, expected_ids, "渲染", errors)
                    for page_id in expected_ids:
                        page = pages.get(page_id)
                        if not page:
                            continue
                        path = project / page.get("path", "")
                        if not path.is_file():
                            errors.append(f"渲染图缺失：{page_id}")
                            continue
                        if digest(path) != page.get("sha256"):
                            errors.append(f"渲染图已变化：{page_id}")
                        errors += image_errors(path)
                    _validate_review_manifest(project, render, expected_ids, errors)
                    _validate_qa_review(project, render, expected_ids, errors)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, zipfile.BadZipFile, ET.ParseError) as exc:
        errors.append(f"输入或工件无效：{exc}")
    return {
        "project": str(project),
        "status": "failed" if errors else "passed",
        "scope": "spec" if spec_only else mode,
        "errors": errors,
        "warnings": ["阶段 3.3 须逐页审阅成品美观度；可按工作流授权优化元素位置，记录调整后重新构建、渲染并签署当前版本。"],
        "slides": audit,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir")
    parser.add_argument("--mode", choices=["draft", "release"], default="draft")
    parser.add_argument("--spec-only", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()
    result = validate(Path(args.project_dir).resolve(), args.mode, args.spec_only)
    if args.output:
        write_json(args.output, result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
