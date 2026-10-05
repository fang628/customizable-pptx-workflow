"""Isolated regression tests; user approvals and provider calls are fixtures only."""
import argparse
import copy
from datetime import datetime, timezone
import io
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from PIL import Image, ImageDraw
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared/scripts"))
sys.path.insert(0, str(ROOT / "stages/33-build/scripts"))
from workflow_lib import (
    ai_image_config_errors,
    candidate_style_errors,
    preview_palette_errors,
    ratio_tokens,
    approval_errors,
    design_errors,
    digest,
    generation_evidence_errors,
    generation_jobs_errors,
    generation_ledger_errors,
    image_plan_trace_errors,
    page_split_rows,
    page_textbox_shapes,
    preview_pages_errors,
    preview_prompt_errors,
    preview_prompt_forbidden_details,
    preview_prompt_height_matches_content,
    read_json,
    speaker_script_errors,
    SPECIAL_SPLITS,
    split_entries,
    spec_errors,
    write_json,
)
from crop_asset import crop_asset
from preview_images import (
    asset_image_errors,
    image_errors,
    normalize,
    stage_preview_errors,
)
from units import inch_to_px, normalized_box_to_inches, normalized_box_to_px, pixel_box_to_inches, px_to_inch
from qa_rules import PREVIEW_TO_NATIVE_SHAPES, text_role
from text_metrics import text_metrics
from shape_masks import boundary_mask
from preview_originals import compose, insertion_errors
from validate_project import inspect_pptx, validate
NODE = "node"
ENV = {**os.environ, "PYTHONUTF8": "1"}
def visual_box(slide, element_id):
    """Normalized box -> pixel corners, for tests that inspect the preview."""
    element = next(item for item in slide["elements"] if item["id"] == element_id)
    box = element["box"]
    return (
        box["x"] * 1920,
        box["y"] * 1080,
        (box["x"] + box["w"]) * 1920,
        (box["y"] + box["h"]) * 1080,
    )
class WorkflowTests(unittest.TestCase):
    TEXT_ROLE_SIZES = {
        "title": (72, 0.14),
        "subtitle": (48, 0.095),
        "section": (52, 0.1),
        "body": (36, 0.075),
        "caption": (28, 0.06),
        "label": (24, 0.055),
        "source": (22, 0.05),
        "page-number": (20, 0.045),
    }
    TEXT_ROLE_TOKENS = [
        ("SUBTITLE", "subtitle"),
        ("KICKER", "label"),
        ("TITLE", "title"),
        ("HEADING", "section"),
        ("SECTION", "section"),
        ("PANELTEXT", "body"),
        ("BODY", "body"),
        ("TEXT", "body"),
        ("SOURCE", "source"),
        ("FOOTER", "source"),
        ("PAGE", "page-number"),
        ("CAPTION", "caption"),
        ("LABEL", "label"),
    ]

    def run_python(self, relative, *args, success=True):
        process = subprocess.run([sys.executable, str(ROOT / relative), *map(str, args)], capture_output=True, encoding="utf-8", env=ENV)
        if success is None:
            return process
        if success:
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        else:
            self.assertNotEqual(process.returncode, 0, process.stdout + process.stderr)
        return process

    def workflow(self, *args, **kwargs):
        return self.run_python("shared/scripts/workflow.py", self.project, *args, **kwargs)

    def build(self, release=False, success=True):
        process = subprocess.run([NODE, str(ROOT / "stages/33-build/scripts/build_pptx.js"), str(self.project),
                                  "--python", sys.executable, "--mode", "release" if release else "draft"],
                                 capture_output=True, encoding="utf-8", env=ENV)
        self.assertEqual(process.returncode == 0, success, process.stdout + process.stderr)
        return process

    def save_spec(self):
        write_json(self.spec_path, self.spec)

    def register_material(self, identifier, path, kind, external=False):
        args = ["material", "--id", identifier, "--path", str(path), "--kind", kind]
        if external:
            args.append("--allow-external-upload")
        return self.workflow(*args)

    def install_test_photo(self, crop=None):
        photo = self.project / "00_intake/materials/photos/planned.png"
        Image.new("RGB", (100, 100), "red").save(photo)
        self.register_material("PHOTO-001", photo, "photo")
        element = {
            "id": "S01-PHOTO-01",
            "type": "image",
            "sourceId": "PHOTO-001",
            "path": photo.relative_to(self.project).as_posix(),
            "x": 7.4,
            "y": 1.2,
            "w": 4.4,
            "h": 4.4,
            "fit": "cover",
            "altText": "计划图片测试",
        }
        if crop:
            element["crop"] = crop
        self.spec["slides"][0]["elements"] = [
            {"id": "S01-TITLE-01", "type": "text", "text": "图片计划测试", "x": .5, "y": .2, "w": 3, "h": .5},
            element,
        ]
        self.sync_contracts()
        return photo

    def sync_contracts(self, include_toc=True):
        """Rebuild design contracts from the current deck spec for isolated fixtures."""
        width, height = (13.333333, 7.5)
        reference_categories = {
            category["id"]: category
            for category in read_json(
                ROOT / "stages/13-design/references/reference-categories.json"
            )["categories"]
        }
        content_slides = []
        claim_slides = []
        plan_slides = []
        intent_slides = []
        for index, slide in enumerate(self.spec["slides"]):
            texts = [
                {"id": element["id"], "text": element["text"]}
                for element in slide["elements"]
                if element["type"] == "text"
            ]
            if index == 0:
                page_type, layout_id = "title", "T01"
            elif index == 1 and include_toc:
                page_type, layout_id = "toc", "D02"
            else:
                page_type, layout_id = "content", "C01"
            category_id = f"{page_type}-{layout_id}"
            category = reference_categories[category_id]
            content_slides.append({
                "id": slide["id"],
                "page_type": page_type,
                "layout_id": layout_id,
                "reference_ids": category["reference_ids"][:1],
                "reference_categories": [category_id],
                "title": texts[0]["text"] if texts else "测试页面",
                "texts": texts or [{"id": f"{slide['id']}-TEXT", "text": "测试文案"}],
                "materials": [],
            })
            claim_slides.append({"id": slide["id"], "claims": []})
            images = []
            intent_images = []
            for element in slide["elements"]:
                if element["type"] != "image" or element.get("origin", "planned") != "planned":
                    continue
                element.setdefault("sourceId", f"GEN-{element['id']}")
                element.setdefault("fit", "contain")
                element.setdefault("altText", f"{element['id']} 测试图片")
                box = normalized_box_to_inches(
                    {
                        "x": element["x"] / width,
                        "y": element["y"] / height,
                        "w": element["w"] / width,
                        "h": element["h"] / height,
                    },
                    width,
                    height,
                )
                normalized = {
                    "x": box["x"] / width,
                    "y": box["y"] / height,
                    "w": box["w"] / width,
                    "h": box["h"] / height,
                }
                item = {
                    "id": element["id"],
                    "sourceId": element["sourceId"],
                    "description": element["altText"],
                    "path": element["path"],
                    "box": normalized,
                    "pixelBox": normalized_box_to_px(normalized),
                    "fit": element["fit"],
                    "z": element.get("z", 0),
                    "altText": element["altText"],
                    "reason": "测试图片计划",
                    "placeholder": {
                        "color": "#E8ECF0",
                        "label": element["sourceId"],
                        "border": "#AAB2BD",
                    },
                }
                if element.get("focal"):
                    item["focal"] = element["focal"]
                if element.get("crop"):
                    item["crop"] = element["crop"]
                if element.get("boundaryMask"):
                    item["boundaryMask"] = copy.deepcopy(element["boundaryMask"])
                images.append(item)
                intent_images.append({
                    "id": element["id"],
                    "sourceId": element["sourceId"],
                    "description": element["altText"],
                    "plannedPath": element["path"],
                    "role": "evidence",
                    "placement": {
                        "region": "center",
                        "relation": "位于测试页面的核心图片区",
                    },
                    "relativeSize": "medium",
                    "fitIntent": element["fit"],
                    "focalIntent": "以主体中心为准",
                    "cropIntent": "优先保留完整主体",
                    "layer": "content",
                    "placeholder": {
                        "label": element["sourceId"],
                        "hint": "阶段 3.3 插入指定图片",
                    },
                    "altText": element["altText"],
                    "reason": "测试图片意图",
                })
            plan_slides.append({"id": slide["id"], "images": images})
            intent_slides.append({"id": slide["id"], "images": intent_images})
        self.save_spec()
        excluded_page_types = {"title", "toc"}
        sections = []
        used_titles = set()
        for slide in content_slides:
            if slide["page_type"] in excluded_page_types:
                continue
            title = slide["title"]
            if title in used_titles:
                title = f"{title}（{slide['id']}）"
            used_titles.add(title)
            sections.append({
                "id": f"SEC-{len(sections) + 1:02d}",
                "title": title,
                "slide_ids": [slide["id"]],
            })
        write_json(
            self.project / "02_design/content.json",
            {
                "include_toc": include_toc,
                "progress_bar": {
                    "enabled": True,
                    "exclude_page_types": ["title", "toc"],
                },
                "sections": sections,
                "slides": content_slides,
            },
        )
        write_json(self.project / "02_design/claim-map.json", {"version": 1, "slides": claim_slides})
        write_json(
            self.project / "02_design/image-intent-plan.json",
            {
                "version": 1,
                "canvas": {"width": 1920, "height": 1080, "unit": "px", "aspect": "16:9"},
                "slides": intent_slides,
            },
        )
        write_json(
            self.project / "02_design/image-plan.json",
            {
                "version": 1,
                "canvas": {"width": 1920, "height": 1080, "unit": "px", "aspect": "16:9"},
                "slides": plan_slides,
            },
        )
        template = (
            ROOT / "stages/13-design/assets/design-spec.md"
        ).read_text(encoding="utf-8")
        for heading in ("## 目录要求", "## 顶部进度条要求"):
            self.assertIn(heading, template)
        confirmed = "需要；第二页为唯一目录页。" if include_toc else "不需要；全篇无 toc 页面。"
        template = template.replace("待填写", "测试内容")
        content_pages = [
            slide["id"] for slide in content_slides if slide["page_type"] == "content"
        ]
        special_methods = (
            "左中右分块＋斜切分块",
            "上下分块＋弧线分块（横向向上凸）",
            "左右分块＋同心圆分块",
            "左中右分块＋波浪形分块",
            "左右上右下分块＋金字塔形分块",
            "上下分块＋圆弧分块（竖向收腰）",
            "左中右分块＋扇形分块",
            "左右上右下分块＋圆形放射分块",
            "上下分块＋横带分块（中间通栏）",
            "左右分块＋六边形分块（蜂窝）",
        )
        rows = []
        for index, page_id in enumerate(content_pages):
            if index % 3 == 2:
                method, detail = "上下分块", "无"
            else:
                method = special_methods[index % len(special_methods)]
                detail = "倾角约 10°"
            rows.append(
                f"| {page_id} | {method} | 文字 | 图片 | — | 色差／间距 | {detail} |"
            )
        if rows:
            header = "| 页面 | 分块方式（宏观＋分区手法） |"
            template = template.replace(header, "\n".join(rows) + "\n" + header, 1)
        template = template.replace(
            "- **排版分级：** 按《排版分级写法》逐级写全本页元素，并为每段文字写明文本框形状、为每张图片写明图像框比例（没有文本框就写「无文本框」）；并列文本段落统一用同一种形状。格式如下（示例）：",
            "- **排版分级：** 测试内容（文本框：圆角矩形；图像框：按原图比例；无图片）。",
        )
        template = template.replace(
            "- 是否需要目录页：", f"- 是否需要目录页：{confirmed}", 1
        )
        (self.project / "02_design/design-spec.md").write_text(
            template, encoding="utf-8"
        )

    def configure_mock_provider(self):
        config_path = self.project / "00_intake/ai-image-config.json"
        config = read_json(config_path)
        config["credentialsReady"] = True
        config["adapterScript"] = str(ROOT / "tests/mock_imagegen.py")
        write_json(config_path, config)

    def log_prompts(self, stage, jobs):
        """Mirror the run's prompts into the shared prompts log, like a real run."""
        stage_label = {
            "content": "阶段 1.2",
            "concepts": "阶段 2.1",
            "full": "阶段 2.2",
        }[stage]
        path = self.project / "02_design/generation-prompts.md"
        existing = path.read_text(encoding="utf-8") if path.is_file() else "# 生图提示词记录\n"
        if f"## {stage_label}" not in existing:
            existing += f"\n## {stage_label}\n"
        for job in jobs:
            existing += (
                f"\n### {job['id']}（{job['asset_id']}）\n"
                f"- 提示词：{job['prompt']}\n"
                f"- 输出：{job['output']}\n"
            )
        path.write_text(existing, encoding="utf-8")

    def run_generation(self, folder, jobs_path, jobs, stage):
        write_json(
            self.project / jobs_path,
            {"jobs": jobs},
        )
        self.log_prompts(stage, jobs)
        return self.run_python(
            "stages/21-concepts/scripts/run_generation.py",
            self.project,
            "--stage",
            stage,
            "--execute",
        )

    def generate_content_assets(self):
        """Stage 1.2 fixture: per-direction candidate images plus the content plan."""
        content = read_json(self.project / "02_design/content.json")
        intent = read_json(self.project / "02_design/image-intent-plan.json")
        boundary = "非事实性示意，不代表真实人物、地点或数据"
        jobs = []
        kind_by_job = {}
        for position, style in enumerate(("a", "b", "c")):
            number = 901 + position * 3
            entries = [
                (
                    f"COVER-{style.upper()}",
                    number,
                    "hero-image",
                    "landscape 16:9 (1920×1080) cover hero image, theme aligned, no text",
                    "封面大图候选（横版）",
                ),
                (
                    f"BACKGROUND-{style.upper()}",
                    number + 1,
                    "content-background",
                    "landscape 16:9 (1920×1080) weak-contrast content background, no text",
                    "内容页弱对比背景底图候选（横版）",
                ),
            ]
            if content.get("include_toc"):
                entries.append((
                    f"TOC-ART-{style.upper()}",
                    number + 2,
                    "toc-image",
                    "landscape 16:9 (1920×1080) realistic art for the contents page, no text",
                    "目录页主图候选（横版、现实风格）",
                ))
            for identifier, digits, kind, prompt, use in entries:
                jobs.append({
                    "id": identifier,
                    "asset_id": f"GEN-{digits}",
                    "prompt": prompt,
                    "output": f"02_design/generated-assets/GEN-{digits}.png",
                    "max_attempts": 1,
                    "intended_use": f"{use}（设计方向 {style}）",
                    "factual_boundary": boundary,
                })
                kind_by_job[identifier] = kind
        self.run_generation(
            "02_design", "02_design/generation-jobs.json", jobs, "content"
        )
        registry = {"version": 1, "assets": []}
        lines = ["# 内容清单", "", "## 封面", "### 主标题", "（封面标题）"]
        for job in jobs:
            path = self.project / job["output"]
            registry["assets"].append({
                "id": job["asset_id"],
                "path": job["output"],
                "sha256": digest(path),
                "kind": kind_by_job[job["id"]],
                "styleId": job["id"].rsplit("-", 1)[-1].lower(),
                "model": "mock-image-1",
                "prompt": job["prompt"],
                "intendedUse": job["intended_use"],
                "factualBoundary": job["factual_boundary"],
            })
            lines.append(f"- 候选图片 {job['asset_id']}：{job['intended_use']}")
        write_json(self.project / "02_design/generated-assets.json", registry)
        lines += ["", "## 正文", "### 结论", "（每页的结论与正文写在这里）"]
        for slide in intent["slides"]:
            for image in slide["images"]:
                lines.append(f"- 计划图片 {image['id']}：{image['description']}")
        (self.project / "02_design/content-plan.md").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )

    def text_entries(self, slide_id):
        """Lay out role-sized text boxes so the fixture satisfies the QA floors."""
        content = read_json(self.project / "02_design/content.json")
        source = next(
            item for item in content["slides"] if item["id"] == slide_id
        )
        entries = [("title", source["title"])] + [
            (item["id"], item["text"]) for item in source["texts"]
        ]
        plan = []
        top = 0.10
        for text_id, text in entries:
            identifier = str(text_id).upper()
            role = "body"
            for token, candidate in self.TEXT_ROLE_TOKENS:
                if token in identifier:
                    role = candidate
                    break
            size, height = self.TEXT_ROLE_SIZES[role]
            measured = text_metrics(
                {"text": text, "fontSize": size, "fontFace": "Microsoft YaHei"},
                (0, 0, round(0.42 * 1920), round(height * 1080)),
            )
            box_height = round(
                max(height, (measured["total_height"] + 6) / 1080), 4
            )
            plan.append((
                text_id,
                text,
                role,
                size,
                {"x": 0.07, "y": round(top, 4), "w": 0.42, "h": box_height},
            ))
            top += box_height + 0.02
        return plan

    def attach_ai_big_images(self):
        """Fixtures must use the three generated big images, like a real deck."""
        hero = "02_design/generated-assets/GEN-901.png"
        background = "02_design/generated-assets/GEN-902.png"
        toc_image = "02_design/generated-assets/GEN-903.png"
        content = read_json(self.project / "02_design/content.json")
        page_type = {slide["id"]: slide["page_type"] for slide in content["slides"]}
        for slide in self.spec["slides"]:
            kind = page_type.get(slide["id"])
            source = None
            if kind == "title":
                source = ("S01-HERO", hero, "GEN-901")
            elif kind == "toc":
                source = ("S02-TOCIMG", toc_image, "GEN-903")
            elif kind in {"content", "thanks"}:
                source = (f"{slide['id']}-BG", background, "GEN-902")
            if not source:
                continue
            element_id, path, source_id = source
            slide["elements"] = [
                item for item in slide["elements"] if item["id"] != element_id
            ]
            slide["elements"].append({
                "id": element_id,
                "type": "image",
                "origin": "reconstruction",
                "sourceId": source_id,
                "path": path,
                "x": 0,
                "y": 0,
                "w": 13.333333,
                "h": 7.5,
                "fit": "cover",
                "altText": "AI 生成大图",
            })
        self.save_spec()

    def write_render(self, matched=True):
        delivery = self.project / "07_delivery"
        deck = delivery / "deck.pptx"
        pages = []
        for slide in self.spec["slides"]:
            preview = self.project / f"04_full-preview/slides/{slide['id']}.png"
            render = delivery / f"preview/{slide['id']}.png"
            render.parent.mkdir(parents=True, exist_ok=True)
            if matched:
                render.write_bytes(preview.read_bytes())
            else:
                Image.new("RGB", (1920, 1080), "#101820").save(render)
            pages.append({
                "id": slide["id"],
                "path": render.relative_to(self.project).as_posix(),
                "sha256": digest(render),
            })
        render_manifest = delivery / "render-manifest.json"
        write_json(render_manifest, {
            "renderer": "TEST FIXTURE",
            "version": "1",
            "rendered_at": "2026-09-18T00:00:00Z",
            "pptx_sha256": digest(deck),
            "width": 1920,
            "height": 1080,
            "pages": pages,
        })
        return render_manifest

    def sign_review(self):
        path = self.project / "07_delivery/qa-review.json"
        review = read_json(path)
        review["reviewer"] = "TEST FIXTURE"
        review["reviewed_at"] = "2026-09-18T00:00:00Z"
        for page in review["pages"]:
            for key in ("visual", "content", "photos", "editability", "preview_match"):
                page[key] = True
            page.update({
                "review_mode": "manual",
                "confidence": 1,
                "human_signed": True,
                "notes": "测试夹具逐页人工签署",
            })
        write_json(path, review)
        return review

    def mutate_package(self, callback):
        location = self.project / "07_delivery/deck.pptx"
        with zipfile.ZipFile(location) as archive:
            members = {name: archive.read(name) for name in archive.namelist()}
        callback(members)
        with zipfile.ZipFile(location, "w") as archive:
            for name, data in members.items():
                archive.writestr(name, data)

    def append_content_slide(self, slide_id, title):
        self.spec["slides"].append({
            "id": slide_id,
            "background": {"color": "FFFFFF"},
            "notes": [],
            "elements": [{
                "id": f"{slide_id}-TITLE-01",
                "type": "text",
                "text": title,
                "x": .6,
                "y": .5,
                "w": 4,
                "h": .6,
                "fontFace": "Microsoft YaHei",
                "fontSize": 28,
                "color": "18212B",
            }],
        })
        self.save_spec()

    def append_content_slide_with_toc(self, slide_id, title):
        """Append a content page and mirror its section title on the TOC page."""
        self.append_content_slide(slide_id, title)
        toc = self.spec["slides"][1]
        toc["elements"].append({
            "id": f"S02-TOC-{slide_id}",
            "type": "text",
            "text": title,
            "x": .7,
            "y": 1.6,
            "w": 4,
            "h": .5,
            "fontFace": "Microsoft YaHei",
            "fontSize": 24,
            "color": "18212B",
        })
        self.save_spec()

    def placeholder_entries(self, page_id):
        """Preview fixture: the placeholder block each planned image keeps in the preview."""
        plan = read_json(self.project / "02_design/image-plan.json")
        slide = next(item for item in plan["slides"] if item["id"] == page_id)
        return [
            {"imageId": image["id"], "box": image["box"]} for image in slide["images"]
        ]

    def preview_page_ids(self, stage):
        """阶段 2.1 取代表页（封面＋目录页＋一页内容页），阶段 2.2 取全部页面。"""
        content = read_json(self.project / "02_design/content.json")
        ids = [slide["id"] for slide in content["slides"]]
        if stage == "2.2":
            return ids
        page_type = {slide["id"]: slide["page_type"] for slide in content["slides"]}
        picked = [ids[0]] if ids else []
        toc = next((sid for sid in ids if page_type.get(sid) == "toc"), None)
        if toc and toc not in picked:
            picked.append(toc)
        body = next((sid for sid in ids if page_type.get(sid) == "content"), None)
        if body and body not in picked:
            picked.append(body)
        return picked

    def preview_prompt(self, context, stage, option, page_id, tag):
        """Whole-page prompt written as numbered points (TEST FIXTURE ONLY)."""
        slide = context["slides"][page_id]
        texts = slide.get("texts") or []
        text_note = "；".join(f"{text['id']}={text['text']}" for text in texts)
        shapes = context["shapes"].get(page_id) or []
        if shapes:
            text_note += f"；文本框形状：{'、'.join(shapes)}"
        if text_note:
            text_note += "；"
        cell = context["split_cells"].get(page_id, "")
        layout_note = (
            f"分块方式 {cell}：按设计稿的方向、走向与弯曲程度，不要简化成直线；"
            if cell
            else "按设计稿的分块排布；"
        )
        layout_note += "元素位置与大小按设计稿的归一化框。"
        layout_note += "文本框高度与实际文本高度匹配，仅保留适量内边距，避免框内大片留白。"
        ratio_note = context["ratio_notes"].get(page_id, "")
        box_note = context["box_notes"].get(page_id, "")
        if ratio_note or box_note:
            ratio_point = "；".join(
                part
                for part in (
                    f"图片位比例 {ratio_note}" if ratio_note else "",
                    "占位块比例不得改变（不拉伸、不变形），按原件比例画占位块，不要插入真图",
                )
                if part
            ) + "。"
        else:
            ratio_point = "本页无计划图片，不画占位块。"
        style_point = (
            f"{'第 ' + option + ' 版' if option else '选定版'}的主色、字体气质与装饰语言统一；"
            "背景与装饰用与所给大图相近的颜色（同一套配色）。"
            "背景与文本框填充色有适度色差，避免强烈反差；描边色单独处理，文字清晰可读。"
        )
        progress_point = (
            "无进度条。"
            if slide.get("page_type") in context["excluded"]
            else "条内逐段写出全部小节标题，当前小节加粗放大，分段有色差。"
        )
        return "\n".join([
            f"{tag} {page_id} whole-page preview following the design spec of {page_id}: "
            "same blocks, text boxes with the design shapes",
            "① 比例要求：16:9 画布（1920×1080）。",
            f"② 内容要求：最终文字：{text_note}"
            "文字只用于表达内容与语义角色；明确标题、正文与注释。",
            f"③ 排版要求：{layout_note}",
            f"④ 图片占位框比例：{ratio_point}",
            f"⑤ 风格要求：{style_point}",
            f"⑥ 进度条要求：{progress_point}",
        ])

    def prompt_suffix(self, page_id, option="a", stage="2.1"):
        """Point-structured clauses that pass the prompt self-check (TEST FIXTURE ONLY)."""
        context = self.preview_context(stage, option)
        tag = f"CONCEPT-{option.upper()}" if stage == "2.1" else "FULL"
        return self.preview_prompt(context, stage, option, page_id, tag)

    def preview_context(self, stage, option=None):
        """Fixture context for whole-page preview prompts: blocks, ratios, texts, shapes."""
        self.run_python("shared/scripts/prepare_split_references.py", self.project)
        split_refs = {
            page["id"]: list(page["references"])
            for page in read_json(self.project / "02_design/split-references.json")["pages"]
        }
        split_cells = dict(
            page_split_rows(
                (self.project / "02_design/design-spec.md").read_text(encoding="utf-8")
            )
        )
        plan = read_json(self.project / "02_design/image-plan.json")
        ratio_notes = {}
        box_notes = {}
        for slide in plan["slides"]:
            tokens = []
            boxes = []
            for image in slide["images"]:
                target = self.project / image["path"]
                if not target.is_file():
                    continue
                with Image.open(target) as opened:
                    aspect = opened.width / opened.height
                tokens += sorted(
                    token for token in ratio_tokens(aspect) if ":" in token and "." not in token
                )
                box = image.get("box") or {}
                boxes.append(
                    f"{image['id']}={box['x']:.4f},{box['y']:.4f},"
                    f"{box['w']:.4f},{box['h']:.4f}"
                )
            if tokens:
                ratio_notes[slide["id"]] = "、".join(sorted(set(tokens))[:2])
            if boxes:
                box_notes[slide["id"]] = "，".join(boxes)
        content = read_json(self.project / "02_design/content.json")
        return {
            "split_refs": split_refs,
            "split_cells": split_cells,
            "ratio_notes": ratio_notes,
            "box_notes": box_notes,
            "slides": {slide["id"]: slide for slide in content["slides"]},
            "excluded": set(
                (content.get("progress_bar") or {}).get("exclude_page_types") or []
            ),
            "shapes": page_textbox_shapes(
                (self.project / "02_design/design-spec.md").read_text(encoding="utf-8")
            ),
        }

    def preview_job(self, context, stage, option, page_id, number):
        """One whole-page job whose prompt carries every point the pre-check requires."""
        folder = "03_concepts" if stage == "2.1" else "04_full-preview"
        tag = f"CONCEPT-{option.upper()}" if stage == "2.1" else "FULL"
        return {
            "id": f"{tag}-{page_id}",
            "asset_id": f"GEN-{number:03d}",
            "prompt": self.preview_prompt(context, stage, option, page_id, tag),
            "output": f"{folder}/assets/GEN-{number:03d}.png",
            "max_attempts": 1,
            "asset_mode": "crop",
            "intended_use": f"{page_id} 的整页预览（AI 生成，按设计稿 {page_id} 排版）",
            "factual_boundary": "整页预览为 AI 生成示意，不代表真实人物、地点或数据",
            "references": context["split_refs"].get(page_id, []),
        }

    def preview_jobs(self, stage, option=None, base=300):
        """Whole-page generation jobs that follow the design spec and split references."""
        context = self.preview_context(stage, option)
        return [
            self.preview_job(context, stage, option, page_id, base + index)
            for index, page_id in enumerate(self.preview_page_ids(stage))
        ]

    def place_preview_page(self, stage, option, page_id, asset_id):
        folder = "03_concepts" if stage == "2.1" else "04_full-preview"
        if stage == "2.1":
            relative = f"03_concepts/option-{option}/{page_id}.png"
        else:
            relative = f"04_full-preview/slides/{page_id}.png"
        target = self.project / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((self.project / f"{folder}/assets/{asset_id}.png").read_bytes())
        return relative, digest(target)

    def generate_concept_set(self):
        """Stage 2.1 fixture: three design directions, each with whole-page previews."""
        jobs = []
        plan = {}
        for position, option in enumerate("abc"):
            entries = []
            for job in self.preview_jobs("2.1", option, base=300 + position * 20):
                jobs.append(job)
                entries.append((job["id"].rpartition("-")[2], job["asset_id"]))
            plan[option] = entries
        self.run_generation(
            "03_concepts", "03_concepts/generation-jobs.json", jobs, "concepts"
        )
        for option, entries in plan.items():
            pages = []
            page_type = {
                slide["id"]: slide["page_type"]
                for slide in read_json(self.project / "02_design/content.json")["slides"]
            }
            for page_id, asset_id in entries:
                relative, sha = self.place_preview_page("2.1", option, page_id, asset_id)
                entry = {
                    "id": page_id,
                    "file": relative,
                    "jobId": f"CONCEPT-{option.upper()}-{page_id}",
                    "sha256": sha,
                    "promptSummary": f"按设计稿 {page_id} 的分块、文字层级与图片位生成整页预览",
                }
                placeholders = self.placeholder_entries(page_id)
                if placeholders:
                    entry["placeholders"] = placeholders
                pages.append(entry)
            write_json(self.project / f"03_concepts/option-{option}/preview.json", {
                "version": 1,
                "stage": "2.1",
                "option": option,
                "styleDirection": f"方向 {option}：从六种候选风格中选出的第 {option.upper()} 号方向",
                "pages": pages,
            })
    def generate_full_preview(self):
        """Stage 2.2 fixture: every page as an AI whole-page preview."""
        jobs = self.preview_jobs("2.2", base=500)
        self.run_generation(
            "04_full-preview", "04_full-preview/generation-jobs.json", jobs, "full"
        )
        page_type = {
            slide["id"]: slide["page_type"]
            for slide in read_json(self.project / "02_design/content.json")["slides"]
        }
        pages = []
        for job in jobs:
            page_id = job["id"].rpartition("-")[2]
            relative, sha = self.place_preview_page("2.2", None, page_id, job["asset_id"])
            entry = {
                "id": page_id,
                "file": relative,
                "jobId": job["id"],
                "sha256": sha,
                "promptSummary": f"按设计稿 {page_id} 的分块、文字层级、图片位与选定风格生成整页预览",
            }
            placeholders = self.placeholder_entries(page_id)
            if placeholders:
                entry["placeholders"] = placeholders
            pages.append(entry)
        write_json(self.project / "04_full-preview/previews.json", {
            "version": 1,
            "stage": "2.2",
            "styleDirection": "方向 b",
            "styleConstraints": (
                "选定方向 b：主色 #2F5D62 ＋ 米白底，标题左对齐、粗圆环与斜向分色装饰，"
                "内容页统一弱对比背景底图，全篇字号层级一致"
            ),
            "pages": pages,
        })
        from preview_originals import insert_pages
        insert_pages(self.project)
        inserted = read_json(self.project / "04_full-preview/previews.json")
        for page in inserted['pages']:
            page['review'] = 'TEST FIXTURE ONLY: synthetic original insertion reviewed'
        write_json(self.project / "04_full-preview/previews.json", inserted)
    def approved_fixture(self, through="3.2", include_toc=True):
        # Explicitly synthetic approval evidence, never used in a real project.
        self.sync_contracts(include_toc=include_toc)
        self.configure_mock_provider()
        self.workflow("await", "1.1", "--notes", "TEST FIXTURE ONLY")
        self.workflow("approve", "requirements", "--evidence", "TEST FIXTURE ONLY")
        self.workflow("complete", "1.1")
        self.generate_content_assets()
        self.workflow("complete", "1.2")
        if through == "1.2":
            return
        self.workflow("await", "1.3", "--notes", "TEST FIXTURE ONLY")
        self.workflow("complete", "1.3")
        if through == "1.3":
            return
        self.generate_concept_set()
        self.workflow("await", "2.1", "--notes", "TEST FIXTURE ONLY")
        self.workflow("approve", "concept", "--option", "b", "--evidence", "TEST FIXTURE ONLY")
        self.workflow("complete", "2.1")
        if through == "2.1":
            return
        self.generate_full_preview()
        self.workflow("await", "2.2", "--notes", "TEST FIXTURE ONLY")
        self.workflow("approve", "preview", "--evidence", "TEST FIXTURE ONLY")
        self.workflow("complete", "2.2")
        if through == "2.2":
            return
        self.attach_ai_big_images()
        assets_path = self.project / "05_reconstruction/assets.json"
        assets = read_json(assets_path)
        indexed = {item["path"] for item in assets["assets"]}
        for slide in self.spec["slides"]:
            for element in slide["elements"]:
                if element["type"] == "image" and element["sourceId"].startswith("GEN-") and element["path"] not in indexed:
                    assets["assets"].append({
                        "path": element["path"],
                        "sha256": digest(self.project / element["path"]),
                        "sourceId": element["sourceId"],
                    })
        write_json(assets_path, assets)
        for stage in ("3.1", "3.2"):
            self.workflow("complete", stage)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="pptx-regression-")
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name)
        self.run_python("stages/00-init/scripts/init_project.py", self.project)
        self.spec_path = self.project / "06_build/deck-spec.json"
        self.spec = read_json(self.spec_path)
        self.spec["slides"].append({
            "id": "S02",
            "background": {"color": "FFFFFF"},
            "notes": [],
            "elements": [{
                "id": "S02-TITLE-01",
                "type": "text",
                "text": "测试目录",
                "x": 0.7,
                "y": 0.6,
                "w": 4,
                "h": 0.7,
                "fontFace": "Microsoft YaHei",
                "fontSize": 28,
                "color": "18212B",
            }],
        })
        report = self.project / "00_intake/materials/reports/report.txt"
        report.write_text("测试材料\n", encoding="utf-8")
        self.register_material("REPORT-001", report, "report")
        self.sync_contracts()

    def test_packaged_files_have_no_machine_specific_paths(self):
        """随 skill 分发的文件不能写死本机绝对路径（换机器就会“找不到路径”）。"""
        offenders = []
        skip_dirs = {"node_modules", "work", "tests", "__pycache__"}
        for base in ("SKILL.md", "package.json", "cli", "shared", "stages"):
            target = ROOT / base
            paths = [target] if target.is_file() else [
                item for item in target.rglob("*") if item.is_file()
            ]
            for path in paths:
                if skip_dirs & set(path.relative_to(ROOT).parts) or path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif"}:
                    continue
                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                for marker in ("C:/Users/", "C:\\Users\\", "Desktop/新建文件夹"):
                    if marker in text:
                        offenders.append(f"{path.relative_to(ROOT)}: {marker}")
                        break
        self.assertEqual(offenders, [])

    def test_default_image_model_is_gpt_image_2(self):
        config = read_json(self.project / "00_intake/ai-image-config.json")
        self.assertEqual(config["provider"], "vsakura")
        self.assertEqual(config["model"], "gpt-image-2")
        self.assertEqual(config["credentialEnv"], "VSAKURA_API_KEY")

    def test_init_additive_and_chinese(self):
        original = self.project / "00_intake/project-brief.md"
        original.write_text("# 用户原有内容", encoding="utf-8")
        result = self.run_python("stages/00-init/scripts/init_project.py", self.project)
        self.assertEqual(json.loads(result.stdout)["created_count"], 0)
        self.assertEqual(original.read_text(encoding="utf-8"), "# 用户原有内容")

    def test_schema_rejects_bad_root_and_unknown_type(self):
        for bad in [[], None, {"slides": []}]:
            write_json(self.spec_path, bad)
            report = validate(self.project, spec_only=True)
            self.assertEqual(report["status"], "failed")
        self.spec["slides"][0]["elements"][0]["type"] = "unknown"
        self.save_spec()
        self.assertEqual(validate(self.project, spec_only=True)["status"], "failed")

    def test_missing_image_path_and_geometry_fail(self):
        for item in [{"id": "bad", "type": "image", "x": 0, "y": 0, "w": 1, "h": 1}, {"id": "bad", "type": "text", "text": "x"}]:
            spec = copy.deepcopy(self.spec)
            spec["slides"][0]["elements"].append(item)
            write_json(self.spec_path, spec)
            self.assertEqual(validate(self.project, spec_only=True)["status"], "failed")

    def test_bounds_and_finite_numbers(self):
        for value in [-10, float("nan"), float("inf")]:
            self.spec["slides"][0]["elements"][0]["x"] = value
            self.save_spec()
            self.assertEqual(validate(self.project, spec_only=True)["status"], "failed")

    def test_draft_build_and_structure(self):
        self.build()
        result = validate(self.project)
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual(result["slides"][0]["native_texts"], 4)

    def test_release_rejects_unapproved(self):
        self.build(release=True, success=False)
        self.assertEqual(validate(self.project, mode="release", spec_only=True)["status"], "failed")

    def test_fake_zip_rejected(self):
        with zipfile.ZipFile(self.project / "07_delivery/deck.pptx", "w") as archive:
            archive.writestr("[Content_Types].xml", "not XML")
            archive.writestr("ppt/presentation.xml", "not XML")
        self.assertEqual(validate(self.project)["status"], "failed")

    def test_zero_slides_in_valid_xml_rejected(self):
        self.build()
        def modify(members):
            root = ET.fromstring(members["ppt/presentation.xml"])
            ns = "http://schemas.openxmlformats.org/presentationml/2006/main"
            root.find(f"{{{ns}}}sldIdLst").clear()
            members["ppt/presentation.xml"] = ET.tostring(root)
        self.mutate_package(modify)
        self.assertEqual(validate(self.project)["status"], "failed")

    def test_invalid_xml_and_broken_relationship_rejected(self):
        self.build()
        self.mutate_package(lambda members: members.update({"ppt/slides/slide1.xml": b"invalid"}))
        self.assertEqual(validate(self.project)["status"], "failed")
        self.build()
        self.mutate_package(lambda members: members.pop("ppt/slideLayouts/slideLayout1.xml"))
        self.assertEqual(validate(self.project)["status"], "failed")

    def test_text_change_detected(self):
        self.build()
        self.spec["slides"][0]["elements"][1]["text"] = "被改动的文字"
        self.save_spec()
        self.assertEqual(validate(self.project)["status"], "failed")

    def test_custom_canvas_and_z_order(self):
        self.spec["meta"] = {"layout": "CUSTOM", "width": 10, "height": 8}
        # 文字被色块完全套住就是文本框：文字必须在框中心（align/valign 都要居中）
        elements = [{"id": "TOP", "type": "text", "text": "顶层", "x": 1, "y": 1, "w": 3, "h": 1, "z": 20,
                     "align": "center", "valign": "middle"},
                    {"id": "BOTTOM", "type": "shape", "shape": "rect", "x": 1, "y": 1, "w": 3, "h": 1, "z": -1}]
        self.spec["slides"][0]["elements"] = elements
        self.save_spec()
        self.build()
        self.assertEqual(validate(self.project)["status"], "passed")
        with zipfile.ZipFile(self.project / "07_delivery/deck.pptx") as archive:
            xml = archive.read("ppt/slides/slide1.xml").decode()
            self.assertLess(xml.index('name="BOTTOM"'), xml.index('name="TOP"'))

    def test_image_cover_and_contain(self):
        photo = self.project / "00_intake/materials/photos/source.png"
        image = Image.new("RGB", (600, 300), "red")
        image.paste("blue", (300, 0, 600, 300))
        image.save(photo)
        self.register_material("PHOTO-001", photo, "photo")
        self.spec["slides"][0]["elements"] = [
            {"id": "LABEL", "type": "text", "text": "图片适配测试", "x": .5, "y": .2, "w": 3, "h": .5},
            {"id": "COVER", "type": "image", "sourceId": "PHOTO-001", "path": photo.relative_to(self.project).as_posix(),
             "x": 7.4, "y": 1.2, "w": 4.4, "h": 4.4, "fit": "cover", "focal": {"x": 1, "y": .5}, "altText": "封面测试图"},
            {"id": "CONTAIN", "type": "image", "sourceId": "PHOTO-001", "path": photo.relative_to(self.project).as_posix(),
             "x": 4, "y": 1, "w": 2, "h": 2, "fit": "contain", "altText": "完整测试图"}]
        self.sync_contracts()
        self.build()
        manifest = read_json(self.project / "07_delivery/build-manifest.json")
        self.assertEqual(manifest["assets"][0]["crop"], {"left": 300, "top": 0, "width": 300, "height": 300})
        self.assertIsNone(manifest["assets"][1]["crop"])
        self.assertEqual(validate(self.project)["status"], "passed")

    def test_native_table_chart_and_svg(self):
        self.spec["slides"][0]["elements"] = [
            {"id": "TABLE", "type": "table", "x": .5, "y": .5, "w": 4, "h": 2, "rows": [["项目", "数量"], ["阶段一", "12"]], "fontFace": "Microsoft YaHei", "fontSize": 16},
            {"id": "CHART", "type": "chart", "chartType": "bar", "x": 5, "y": .5, "w": 5, "h": 3, "data": [{"name": "数量", "labels": ["甲", "乙"], "values": [12, 18]}]},
            {"id": "VECTOR", "type": "svg", "x": 1, "y": 4, "w": 1, "h": 1, "svg": '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100"><circle cx="50" cy="50" r="40" fill="#278470"/></svg>'}]
        self.save_spec()
        self.build()
        result = validate(self.project)
        self.assertEqual(result["status"], "passed", result)

    def test_bad_svg_rejected(self):
        self.spec["slides"][0]["elements"] = [{"id": "V", "type": "svg", "x": 1, "y": 1, "w": 1, "h": 1, "svg": '<svg><image href="https://example.com/a.png"/></svg>'}]
        self.save_spec()
        self.assertEqual(validate(self.project, spec_only=True)["status"], "failed")

    def test_generated_asset_registration_and_hash_validation(self):
        asset = self.project / "02_design/generated-assets/GEN-001/decor.png"
        asset.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", (64, 64), (30, 140, 110, 255)).save(asset)
        inventory_path = self.project / "02_design/generated-assets.json"
        inventory = read_json(inventory_path)
        inventory["assets"].append({
            "id": "GEN-001",
            "path": asset.relative_to(self.project).as_posix(),
            "sha256": digest(asset),
            "kind": "texture",
            "model": "TEST FIXTURE",
            "prompt": "非事实性抽象纹理",
            "intendedUse": "作为封面装饰候选",
            "factualBoundary": "不包含人物、地点、实验证据或标识",
            "sourceReferences": ["REPORT-001"],
        })
        write_json(inventory_path, inventory)
        self.assertFalse(design_errors(self.project))
        Image.new("RGBA", (64, 64), (120, 30, 50, 255)).save(asset)
        self.assertTrue(any("文件版本已变化" in error for error in design_errors(self.project)))

    def test_unregistered_generated_asset_is_rejected(self):
        asset = self.project / "02_design/generated-assets/GEN-999/decor.png"
        asset.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", (64, 64), (30, 80, 160, 255)).save(asset)
        self.spec["slides"][0]["elements"].append({
            "id": "S01-PHOTO-99",
            "type": "image",
            "sourceId": "GEN-999",
            "path": asset.relative_to(self.project).as_posix(),
            "x": 10,
            "y": 5,
            "w": 1,
            "h": 1,
            "fit": "contain",
            "altText": "未登记生成素材测试",
        })
        self.sync_contracts()
        self.assertTrue(any("未登记生成素材：GEN-999" in error for error in design_errors(self.project)))

    def test_every_generation_prompt_is_logged(self):
        self.approved_fixture(through="1.2")
        log_path = self.project / "02_design/generation-prompts.md"
        self.assertTrue(log_path.is_file())
        logged = log_path.read_text(encoding="utf-8")
        jobs = read_json(self.project / "02_design/generation-jobs.json")["jobs"]
        for job in jobs:
            self.assertIn(job["id"], logged)
        self.assertIn("## 阶段 1.2", logged)

        self.generate_concept_set()
        logged = log_path.read_text(encoding="utf-8")
        self.assertIn("## 阶段 2.1", logged)

        # 少记一个任务就要被拒
        jobs = read_json(self.project / "03_concepts/generation-jobs.json")["jobs"]
        stripped = logged.replace(jobs[0]["id"], "已删除的任务")
        log_path.write_text(stripped, encoding="utf-8")
        rejected = self.workflow("complete", "2.1", success=False)
        self.assertIn("没有记录生图任务", rejected.stderr)

    def test_design_spec_lists_missing_material_and_page_images(self):
        self.approved_fixture(through="1.2")
        spec = (self.project / "02_design/design-spec.md").read_text(encoding="utf-8")
        self.assertIn("## 待补充材料", spec)
        self.assertIn("每页尽量都有图片", spec)

        scope = (ROOT / "stages/12-content/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("尽量保证每一页都有图片", scope)
        self.assertIn("BioRender", scope)
        self.assertIn("保留设计稿规划", scope)

        design = (ROOT / "stages/13-design/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("尽量保证每一页都有图片", design)

        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("尽量保证每一页都有图片", skill)
        self.assertIn("generation-prompts.md", skill)

    def test_progress_bar_text_is_not_part_of_content_texts(self):
        self.append_content_slide_with_toc("S03", "研究背景与问题")
        self.sync_contracts()
        content = read_json(self.project / "02_design/content.json")
        sections = content["sections"]
        self.assertTrue(sections)
        title = sections[0]["title"]
        slide = self.spec["slides"][2]  # S03 内容页
        slide["elements"].append({
            "id": "S03-PROGRESS-01",
            "type": "text",
            "origin": "progress",
            "text": title,
            "x": 1.0,
            "y": 0.15,
            "w": 2.6,
            "h": 0.4,
            "fontFace": "Microsoft YaHei",
            "fontSize": 14,
            "color": "FFFFFF",
        })
        self.save_spec()
        self.assertFalse(spec_errors(self.project, self.spec, release=True))

        # 进度条标题必须逐字取自 sections
        slide["elements"][-1]["text"] = "自造的小节标题"
        self.save_spec()
        errors = spec_errors(self.project, self.spec, release=True)
        self.assertTrue(any("逐字取自 content.json 的 sections" in item for item in errors), errors)

        # 标题页不允许出现进度条文本
        slide["elements"][-1]["text"] = title
        self.spec["slides"][0]["elements"].append(
            dict(slide["elements"][-1], id="S01-PROGRESS-01")
        )
        self.save_spec()
        errors = spec_errors(self.project, self.spec, release=True)
        self.assertTrue(any("不应出现进度条" in item for item in errors), errors)

    def test_build_rules_for_toc_numbers_and_missing_elements(self):
        build = (ROOT / "stages/33-build/SKILL.md").read_text(encoding="utf-8")
        for item in (
            "分开成两个单独的文本框",
            "标号字号比小标题略大一点",
            "在文本框中心",
            "不能省略",
            "裁切时不要切到画面主体",
        ):
            self.assertIn(item, build)

        scope = (ROOT / "stages/13-design/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("主动询问用户补充", scope)
        content = (ROOT / "stages/12-content/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("主动向用户询问补充", content)

        # 图片出处不上页面，但图片旁要有图注，且设计稿包含图注
        for name in (
            "stages/13-design/assets/design-spec.md",
            "stages/13-design/SKILL.md",
            "stages/12-content/SKILL.md",
            "SKILL.md",
        ):
            doc = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn("Sxx-CAPTION-01", doc, name)
        template = (ROOT / "stages/13-design/assets/design-spec.md").read_text(encoding="utf-8")
        self.assertIn("图片说明（页面上的图注文字，要进 `content.json`）", template)
        self.assertIn("不需要在页面上标注出处", template)

    def test_ai_major_images_must_be_used_in_the_deck(self):
        from workflow_lib import ai_major_image_errors

        self.approved_fixture(through="1.2")
        registry = read_json(self.project / "02_design/generated-assets.json")["assets"]
        hero = next(a["id"] for a in registry if a["kind"] == "hero-image")
        toc_image = next(a["id"] for a in registry if a["kind"] == "toc-image")
        background = next(a["id"] for a in registry if a["kind"] == "content-background")
        photo = self.project / "00_intake/materials/photos/ai-hero-test.png"
        Image.new("RGB", (1600, 900), "#2F5D62").save(photo)
        self.register_material("PHOTO-900", photo, "photo")

        failures = ai_major_image_errors(self.project, self.spec)
        self.assertTrue(any("标题图" in item for item in failures), failures)

        def attach(slide, element_id, source_id):
            slide["elements"].append({
                "id": element_id,
                "type": "image",
                "sourceId": source_id,
                "path": photo.relative_to(self.project).as_posix(),
                "x": 0.5,
                "y": 0.5,
                "w": 13.333333,
                "h": 7.5,
                "fit": "cover",
                "altText": "AI 大图",
            })

        attach(self.spec["slides"][0], "S01-HERO-01", hero)
        attach(self.spec["slides"][1], "S02-TOCIMG-01", toc_image)
        self.save_spec()
        self.assertEqual(ai_major_image_errors(self.project, self.spec), [])

        # 追加一页内容页但没有背景底图 → 报错
        self.append_content_slide("S03", "内容页背景测试")
        self.save_spec()
        self.sync_contracts()
        failures = ai_major_image_errors(self.project, self.spec)
        self.assertTrue(any("背景底图" in item for item in failures), failures)

        attach(self.spec["slides"][2], "S03-BG-01", background)
        self.save_spec()
        self.assertEqual(ai_major_image_errors(self.project, self.spec), [])

    def test_reconstruction_image_is_outside_image_plan(self):
        asset = self.project / "05_reconstruction/cutouts/RECON-001.png"
        Image.new("RGBA", (80, 80), (20, 90, 150, 255)).save(asset)
        manifest_path = self.project / "05_reconstruction/assets.json"
        manifest = read_json(manifest_path)
        manifest["assets"].append({
            "path": asset.relative_to(self.project).as_posix(),
            "sha256": digest(asset),
            "sourceId": "RECON-001",
        })
        write_json(manifest_path, manifest)
        self.spec["slides"][0]["elements"].append({
            "id": "S01-DECOR-01",
            "type": "image",
            "origin": "reconstruction",
            "sourceId": "RECON-001",
            "path": asset.relative_to(self.project).as_posix(),
            "x": 10,
            "y": 5,
            "w": 1,
            "h": 1,
            "fit": "contain",
            "preserveAlpha": True,
            "altText": "重建装饰",
        })
        self.save_spec()
        self.sync_contracts()
        plan = read_json(self.project / "02_design/image-plan.json")
        self.assertEqual(plan["slides"][0]["images"], [])
        report = validate(self.project, spec_only=True)
        self.assertEqual(report["status"], "passed", report)

    def test_local_cutout_keeps_transparent_alpha(self):
        source = self.project / "00_intake/materials/photos/cutout-source.png"
        image = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        image.paste((210, 40, 60, 255), (8, 0, 16, 16))
        image.save(source)
        output = self.project / "05_reconstruction/cutouts/decor-cutout.png"
        manifest_path = self.project / "05_reconstruction/assets.json"
        record = crop_asset(
            self.project,
            source,
            output,
            "RECON-001",
            {"x": 0, "y": 0, "width": 1, "height": 1},
            manifest_path=manifest_path,
            description="保留透明通道的装饰局部抠图",
            alpha_mode="keep",
        )
        self.assertEqual(record["alphaMode"], "keep")
        with Image.open(output) as result:
            self.assertEqual(result.mode, "RGBA")
            self.assertEqual(result.getpixel((2, 2))[3], 0)
            self.assertEqual(result.getpixel((12, 2))[3], 255)
        self.assertEqual(read_json(manifest_path)["assets"][0]["sourceId"], "RECON-001")

    def test_external_svg_file_builds_as_independent_object(self):
        vector = self.project / "05_reconstruction/vectors/icon.svg"
        vector.parent.mkdir(parents=True, exist_ok=True)
        vector.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
            '<circle cx="50" cy="50" r="40" fill="#278470"/></svg>',
            encoding="utf-8",
        )
        self.spec["slides"][0]["elements"] = [
            {"id": "TITLE", "type": "text", "text": "SVG 独立对象", "x": .5, "y": .5, "w": 3, "h": .5},
            {
                "id": "S01-VECTOR-01",
                "type": "svg",
                "origin": "reconstruction",
                "sourceId": "RECON-001",
                "path": vector.relative_to(self.project).as_posix(),
                "x": 4,
                "y": 2,
                "w": 1,
                "h": 1,
            },
        ]
        self.save_spec()
        self.build()
        manifest = read_json(self.project / "07_delivery/build-manifest.json")
        relative = vector.relative_to(self.project).as_posix()
        self.assertEqual(manifest["inputs"][relative], digest(vector))
        with zipfile.ZipFile(self.project / "07_delivery/deck.pptx") as archive:
            slide_xml = archive.read("ppt/slides/slide1.xml").decode()
        self.assertIn("<p:pic", slide_xml)
        self.assertIn("S01-VECTOR-01", slide_xml)
        self.assertEqual(validate(self.project)["status"], "passed")

    def test_stage_change_invalidates_downstream(self):
        self.approved_fixture()
        self.assertEqual(validate(self.project, mode="release", spec_only=True)["status"], "passed")
        (self.project / "02_design/design-spec.md").write_text("# 已更改设计", encoding="utf-8")
        self.assertEqual(validate(self.project, mode="release", spec_only=True)["status"], "failed")
        output = self.workflow("status").stdout
        self.assertIn("1.3: stale", output)
        self.assertIn("3.2: stale", output)

    def test_release_build_requires_current_review(self):
        self.approved_fixture()
        self.build(release=True)
        self.assertEqual(validate(self.project, mode="release")["status"], "failed")
        self.write_render(matched=True)
        self.run_python("stages/33-build/scripts/prepare_review.py", self.project)
        self.sign_review()
        result = validate(self.project, mode="release")
        self.assertEqual(result["status"], "passed", result)
        self.workflow("complete", "3.3")
        preview = self.project / "07_delivery/preview/S01.png"
        preview.write_bytes(b"changed")
        self.assertEqual(validate(self.project, mode="release")["status"], "failed")

    def test_design_completion_waits_for_user_review(self):
        self.sync_contracts()
        self.configure_mock_provider()
        self.workflow("await", "1.1", "--notes", "TEST FIXTURE ONLY")
        self.workflow("approve", "requirements", "--evidence", "TEST FIXTURE ONLY")
        self.workflow("complete", "1.1")
        rejected = self.workflow("complete", "1.3", success=False)
        self.assertIn("await 1.3", rejected.stderr)
        status = read_json(self.project / "workflow-state.json")["stages"].get("1.3", {}).get("status")
        self.assertNotEqual(status, "complete")

    def test_preview_completion_waits_for_user_confirmation(self):
        self.approved_fixture(through="2.1")
        self.generate_full_preview()
        self.workflow("await", "2.2", "--notes", "TEST FIXTURE ONLY")
        state = read_json(self.project / "workflow-state.json")["stages"]["2.2"]
        self.assertEqual(state["status"], "awaiting_user")
        rejected = self.workflow("complete", "2.2", success=False)
        self.assertIn("批准", rejected.stderr)
        self.assertFalse((self.project / "04_full-preview/approval.json").exists())
        self.assertEqual(validate(self.project, mode="release", spec_only=True)["status"], "failed")

    def test_image_plan_and_spec_contract_drift_fails(self):
        self.install_test_photo()
        plan_path = self.project / "02_design/image-plan.json"
        self.spec["slides"][0]["elements"][1]["x"] += .2
        self.save_spec()
        self.assertEqual(validate(self.project, spec_only=True)["status"], "failed")
        self.sync_contracts()
        for key, value in (("fit", "contain"), ("z", 9), ("altText", "漂移后的替代文本")):
            plan = read_json(plan_path)
            plan["slides"][0]["images"][0][key] = value
            write_json(plan_path, plan)
            self.assertEqual(validate(self.project, spec_only=True)["status"], "failed", key)
            self.sync_contracts()

    def test_final_image_plan_changes_do_not_invalidate_design_or_concept_approval(self):
        self.install_test_photo()
        self.approved_fixture(through="2.1")
        plan_path = self.project / "02_design/image-plan.json"
        plan = read_json(plan_path)
        plan["slides"][0]["images"][0]["fit"] = "contain"
        write_json(plan_path, plan)
        self.assertFalse(approval_errors(self.project, "concept"))
        self.assertFalse(image_plan_trace_errors(self.project, plan))
        output = self.workflow("status").stdout
        self.assertIn("1.2: complete", output)
        self.assertIn("2.1: complete", output)

    def test_final_image_plan_cannot_change_intent_identity(self):
        self.install_test_photo()
        self.sync_contracts()
        plan_path = self.project / "02_design/image-plan.json"
        plan = read_json(plan_path)
        plan["slides"][0]["images"][0]["sourceId"] = "GEN-CHANGED"
        write_json(plan_path, plan)
        self.assertTrue(any("sourceId" in error for error in image_plan_trace_errors(self.project, plan)))
        plan = read_json(plan_path)
        plan["slides"][0]["images"][0]["sourceId"] = "PHOTO-001"
        plan["slides"][0]["images"][0]["description"] = "被偷换的图片内容"
        write_json(plan_path, plan)
        self.assertTrue(any("图片内容描述" in error for error in image_plan_trace_errors(self.project, plan)))

    def test_requirements_completion_requires_ready_ai_configuration(self):
        self.workflow("await", "1.1", "--notes", "TEST FIXTURE ONLY")
        self.workflow("approve", "requirements", "--evidence", "TEST FIXTURE ONLY")
        config_path = self.project / "00_intake/ai-image-config.json"
        config_path.unlink()
        result = self.workflow("complete", "1.1", success=False)
        self.assertIn("缺少或无效的 AI 生图配置", result.stderr)
        config = {
            "version": 1,
            "provider": "mock",
            "model": "mock-image-1",
            "credentialEnv": "MOCK_IMAGE_API_KEY",
            "credentialsReady": False,
            "allowReferenceUpload": False,
            "stageBudgets": {"1.2": 0, "2.1": 3, "2.2": 4},
            "referenceImageLimit": 0,
            "adapterScript": str(ROOT / "tests/mock_imagegen.py"),
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
        }
        write_json(config_path, config)
        self.assertTrue(any("凭据尚未标记为就绪" in error for error in ai_image_config_errors(self.project)))
        result = self.workflow("complete", "1.1", success=False)
        self.assertIn("凭据尚未标记为就绪", result.stderr)
        config["credentialsReady"] = True
        write_json(config_path, config)
        self.workflow("complete", "1.1")

    def test_concept_approval_requires_real_generation_evidence(self):
        self.approved_fixture(through="1.3")
        self.generate_concept_set()
        (self.project / "03_concepts/generation-ledger.json").unlink()
        result = self.workflow("approve", "concept", "--option", "b", "--evidence", "TEST FIXTURE ONLY", success=False)
        self.assertIn("缺少或无效的生图账本", result.stderr)

    def test_preview_approval_requires_real_generation_evidence(self):
        self.approved_fixture(through="2.1")
        self.generate_full_preview()
        self.workflow("await", "2.2", "--notes", "TEST FIXTURE ONLY")
        (self.project / "04_full-preview/generation-ledger.json").unlink()
        result = self.workflow("approve", "preview", "--evidence", "TEST FIXTURE ONLY", success=False)
        self.assertIn("缺少或无效的生图账本", result.stderr)

    def test_generation_provider_and_model_must_match_configuration(self):
        self.approved_fixture(through="1.3")
        self.generate_concept_set()
        config = read_json(self.project / "00_intake/ai-image-config.json")
        jobs_path = self.project / "03_concepts/generation-jobs.json"
        jobs = read_json(jobs_path)
        jobs["jobs"][0]["model"] = "silent-model-switch"
        write_json(jobs_path, jobs)
        errors = generation_jobs_errors(self.project, "2.1", config)
        self.assertTrue(any("任务模型" in error and "不一致" in error for error in errors), errors)
        jobs["jobs"][0].pop("model")
        write_json(jobs_path, jobs)
        ledger_path = self.project / "03_concepts/generation-ledger.json"
        ledger = read_json(ledger_path)
        ledger["provider"] = "other-provider"
        write_json(ledger_path, ledger)
        errors = generation_ledger_errors(self.project, "2.1", config)
        self.assertTrue(any("生图账本供应商" in error and "不一致" in error for error in errors), errors)
        ledger["provider"] = config["provider"]
        ledger["model"] = "silent-model-switch"
        write_json(ledger_path, ledger)
        errors = generation_ledger_errors(self.project, "2.1", config)
        self.assertTrue(any("生图账本模型" in error and "不一致" in error for error in errors), errors)

    def test_generation_ledger_rejects_tampered_request_and_hashes(self):
        self.approved_fixture(through="1.3")
        self.generate_concept_set()
        ledger_path = self.project / "03_concepts/generation-ledger.json"
        original = read_json(ledger_path)
        identifiers = list(original["jobs"])
        self.assertGreaterEqual(len(identifiers), 1)
        ledger = copy.deepcopy(original)
        ledger["jobs"][identifiers[0]]["sha256"] = "0" * 64
        write_json(ledger_path, ledger)
        errors = generation_ledger_errors(self.project, "2.1")
        self.assertTrue(any("规范化输出哈希已变化" in error for error in errors), errors)
        ledger = copy.deepcopy(original)
        ledger["jobs"][identifiers[0]]["raw_sha256"] = "0" * 64
        write_json(ledger_path, ledger)
        errors = generation_ledger_errors(self.project, "2.1")
        self.assertTrue(any("原始生成图哈希已变化" in error for error in errors), errors)

    def test_invalid_text_options_cannot_build(self):
        element = self.spec["slides"][0]["elements"][1]
        self.assertEqual(element["type"], "text")
        for field, value in (("align", "middle"), ("valign", "center"), ("fit", "cover")):
            candidate = copy.deepcopy(self.spec)
            candidate["slides"][0]["elements"][1][field] = value
            self.assertTrue(spec_errors(self.project, candidate), field)
        element["align"] = "middle"
        self.save_spec()
        self.build(success=False)

    def test_embedded_photo_passes_release_after_review(self):
        self.install_test_photo()
        self.approved_fixture()
        self.build(release=True)
        self.write_render(matched=True)
        self.run_python("stages/33-build/scripts/prepare_review.py", self.project)
        self.sign_review()
        result = validate(self.project, mode="release")
        self.assertEqual(result["status"], "passed", result)
        self.workflow("complete", "3.3")

    def test_compare_images_are_required_before_release(self):
        self.approved_fixture()
        self.build(release=True)
        self.write_render(matched=False)
        self.run_python("stages/33-build/scripts/prepare_review.py", self.project)
        self.sign_review()
        review_path = self.project / "07_delivery/review-manifest.json"
        manifest = read_json(review_path)
        compare_path = self.project / manifest["pages"][0]["compare_path"]
        self.assertTrue(compare_path.is_file())
        compare_path.unlink()
        report = validate(self.project, mode="release")
        self.assertEqual(report["status"], "failed")
        self.assertTrue(any("对照图缺失" in error for error in report["errors"]), report["errors"])

    def test_local_png_cannot_replace_generated_background(self):
        self.approved_fixture(through="2.1")
        self.generate_full_preview()
        previews = read_json(self.project / "04_full-preview/previews.json")
        ledger = read_json(self.project / "04_full-preview/generation-ledger.json")
        output = self.project / ledger["jobs"][previews["pages"][0]["jobId"]]["output"]
        Image.new("RGB", (1920, 1080), "#F4F1E8").save(output)
        errors = generation_evidence_errors(self.project, "2.2")
        self.assertTrue(any("哈希已变化" in error for error in errors), errors)

    def test_qa_review_hash_drift_blocks_release(self):
        self.approved_fixture()
        self.build(release=True)
        self.write_render(matched=True)
        self.run_python("stages/33-build/scripts/prepare_review.py", self.project)
        self.sign_review()
        review_path = self.project / "07_delivery/qa-review.json"
        review = read_json(review_path)
        review["image_plan_sha256"] = "0" * 64
        write_json(review_path, review)
        report = validate(self.project, mode="release")
        self.assertEqual(report["status"], "failed")
        self.assertTrue(any("人工审阅绑定版本已失效" in error for error in report["errors"]))

    def test_preview_match_deviation_requires_complete_approval(self):
        self.approved_fixture()
        self.build(release=True)
        self.write_render(matched=True)
        self.run_python("stages/33-build/scripts/prepare_review.py", self.project)
        self.sign_review()
        review_path = self.project / "07_delivery/qa-review.json"
        review = read_json(review_path)
        page = review["pages"][0]
        page["preview_match"] = False
        page["deviations"] = []
        write_json(review_path, review)
        self.assertEqual(validate(self.project, mode="release")["status"], "failed")
        page["deviations"] = [{
            "type": "preview_difference",
            "region": {"x": 0, "y": 0, "w": 1, "h": 1},
            "severity": "minor",
            "expected": "源预览",
            "actual": "渲染图",
            "reason": "测试夹具记录已知偏差",
            "evidence": "07_delivery/review/S01-compare.png",
            "approved_by": "TEST FIXTURE",
            "approved_at": "2026-09-18T00:00:00Z",
        }]
        write_json(review_path, review)
        self.assertEqual(validate(self.project, mode="release")["status"], "passed")

    def test_crop_out_of_bounds_fails(self):
        self.install_test_photo(crop={"x": .9, "y": 0, "width": .2, "height": 1, "background": "#FFFFFF"})
        report = validate(self.project, spec_only=True)
        self.assertEqual(report["status"], "failed")
        self.assertTrue(any("crop 区域超出原图边界" in error for error in report["errors"]))

    def test_rgba_transparent_pixels_use_normalization_background(self):
        source = self.project / "rgba.png"
        output = self.project / "rgba-preview.png"
        Image.new("RGBA", (100, 100), (0, 0, 0, 0)).save(source)
        record = normalize(source, output, "pad", "#123456")
        self.assertEqual(record["background"], "#123456")
        with Image.open(output) as image:
            self.assertEqual(image.getpixel((960, 540)), (18, 52, 86))

    def test_pixel_inch_and_normalized_conversions(self):
        self.assertAlmostEqual(px_to_inch(144), 1)
        self.assertAlmostEqual(inch_to_px(1), 144)
        self.assertAlmostEqual(normalized_box_to_inches({"x": .5, "y": .25, "w": .1, "h": .2})["x"], 20 / 3)
        self.assertEqual(normalized_box_to_px({"x": .5, "y": .25, "w": .1, "h": .2}), {"x": 960, "y": 270, "w": 192, "h": 216})
        self.assertAlmostEqual(pixel_box_to_inches({"x": 144, "y": 72, "w": 144, "h": 72})["w"], 1)

    def test_build_history_preserves_previous(self):
        self.build()
        before = digest(self.project / "07_delivery/deck.pptx")
        self.build()
        self.assertIn(before, [digest(p) for p in self.project.glob("07_delivery/history/*/deck.pptx")])

    def test_qwen_mock_cache_retry_and_redaction(self):
        self.approved_fixture(through="1.3")
        plan = {
            "jobs": [{
                "id": "A-S01",
                "asset_id": "GEN-501",
                "prompt": "TEST " + self.prompt_suffix("S01"),
                "output": "03_concepts/assets/GEN-501.png",
                "max_attempts": 1,
                "intended_use": "测试生图缓存",
                "factual_boundary": "不包含真实人物、地点或数据",
            }],
        }
        write_json(self.project / "03_concepts/generation-jobs.json", plan)
        args = [self.project, "--stage", "concepts", "--qwen-script", ROOT / "tests/mock_imagegen.py"]
        self.run_python("stages/21-concepts/scripts/run_generation.py", *args)
        self.assertFalse((self.project / "03_concepts/generation-ledger.json").exists())
        self.run_python("stages/21-concepts/scripts/run_generation.py", *args, "--execute")
        self.run_python("stages/21-concepts/scripts/run_generation.py", *args, "--execute")
        ledger = read_json(self.project / "03_concepts/generation-ledger.json")
        self.assertEqual(ledger["attempts"], 1)
        self.assertIsNone(ledger["budget"])
        # 不设次数预算：失败的任务会自动重试，直到成功或达到单任务本轮上限。
        plan["jobs"] = [{
            "id": "FLAKY",
            "asset_id": "GEN-503",
            "prompt": "FLAKY " + self.prompt_suffix("S01"),
            "output": "03_concepts/assets/GEN-503.png",
            "intended_use": "测试失败后自动重试",
            "factual_boundary": "不包含真实人物、地点或数据",
        }]
        write_json(self.project / "03_concepts/generation-jobs.json", plan)
        self.run_python(
            "stages/21-concepts/scripts/run_generation.py",
            *args,
            "--execute",
            "--attempts",
            "4",
        )
        ledger = read_json(self.project / "03_concepts/generation-ledger.json")
        self.assertEqual(ledger["jobs"]["FLAKY"]["attempts"], 3)
        self.assertTrue((self.project / "03_concepts/assets/GEN-503.png").is_file())
        plan["jobs"] = [{
            "id": "FAIL",
            "asset_id": "GEN-502",
            "prompt": "FAIL " + self.prompt_suffix("S01"),
            "output": "03_concepts/assets/GEN-502.png",
            "intended_use": "测试生图失败脱敏",
            "factual_boundary": "不包含真实人物、地点或数据",
        }]
        write_json(self.project / "03_concepts/generation-jobs.json", plan)
        result = self.run_python(
            "stages/21-concepts/scripts/run_generation.py",
            *args,
            "--execute",
            "--attempts",
            "1",
            success=False,
        )
        self.assertNotIn("SENSITIVE_TEST_MARKER", result.stdout + result.stderr)
        self.assertNotIn(
            "SENSITIVE_TEST_MARKER",
            (self.project / "03_concepts/generation-ledger.json").read_text(encoding="utf-8"),
        )
        attempts_before = read_json(
            self.project / "03_concepts/generation-ledger.json"
        )["attempts"]
        self.run_python(
            "stages/21-concepts/scripts/run_generation.py",
            *args,
            "--execute",
            "--attempts",
            "2",
            success=False,
        )
        self.assertEqual(
            read_json(self.project / "03_concepts/generation-ledger.json")["attempts"],
            attempts_before + 2,
        )

    def test_legacy_stage_budgets_are_ignored(self):
        self.sync_contracts()
        config_path = self.project / "00_intake/ai-image-config.json"
        config = read_json(config_path)
        config.update({
            "credentialsReady": True,
            "adapterScript": str(ROOT / "tests/mock_imagegen.py"),
            "stageBudgets": {"1.2": 0, "2.1": 0, "2.2": 0},
        })
        write_json(config_path, config)
        self.workflow("await", "1.1", "--notes", "TEST FIXTURE ONLY")
        self.workflow("approve", "requirements", "--evidence", "TEST FIXTURE ONLY")
        self.workflow("complete", "1.1")
        self.generate_content_assets()
        self.workflow("complete", "1.2")
        self.workflow("await", "1.3", "--notes", "TEST FIXTURE ONLY")
        self.workflow("complete", "1.3")
        write_json(self.project / "03_concepts/generation-jobs.json", {
            "jobs": [{
                "id": "LEGACY",
                "asset_id": "GEN-504",
                "prompt": "TEST " + self.prompt_suffix("S01"),
                "output": "03_concepts/assets/GEN-504.png",
                "intended_use": "测试旧预算字段被忽略",
                "factual_boundary": "不包含真实人物、地点或数据",
            }],
        })
        self.run_python(
            "stages/21-concepts/scripts/run_generation.py",
            self.project,
            "--stage",
            "concepts",
            "--qwen-script",
            ROOT / "tests/mock_imagegen.py",
            "--execute",
            "--attempts",
            "4",
        )
        self.assertTrue((self.project / "03_concepts/assets/GEN-504.png").is_file())
        ledger = read_json(self.project / "03_concepts/generation-ledger.json")
        self.assertIsNone(ledger["budget"])

    def test_unapproved_external_reference_blocked(self):
        photo = self.project / "00_intake/materials/photos/photo.png"
        Image.new("RGB", (100, 100), "red").save(photo)
        self.workflow("material", "--id", "PHOTO-001", "--path", photo, "--kind", "photo")
        self.approved_fixture(through="1.3")
        write_json(self.project / "03_concepts/generation-jobs.json", {"max_total_attempts": 1, "jobs": [{"id": "A", "prompt": "test", "references": ["PHOTO-001"], "output": "03_concepts/option-a/S01.png"}]})
        self.run_python("stages/21-concepts/scripts/run_generation.py", self.project, "--stage", "concepts", "--qwen-script", ROOT / "tests/mock_imagegen.py", success=False)

    def test_review_preparation_never_auto_approves(self):
        self.approved_fixture()
        self.build()
        output = self.project / "07_delivery"
        self.write_render(matched=False)
        self.run_python("stages/33-build/scripts/prepare_review.py", self.project)
        review = read_json(output / "qa-review.json")
        self.assertFalse(review["pages"][0]["visual"])
        self.assertFalse(review["reviewer"])
        self.assertTrue(review["warnings"])
        self.assertFalse(review["pages"][0]["human_signed"])
        self.assertTrue((output / "review/contact-sheet.png").is_file())

    def test_source_photo_change_blocks_release(self):
        photo = self.project / "00_intake/materials/photos/photo.png"
        Image.new("RGB", (100, 100), "red").save(photo)
        self.register_material("PHOTO-001", photo, "photo")
        self.spec["slides"][0]["elements"].append({
            "id": "S01-PHOTO",
            "type": "image",
            "path": photo.relative_to(self.project).as_posix(),
            "sourceId": "PHOTO-001",
            "altText": "来源变更测试图",
            "x": 9.5,
            "y": 5,
            "w": 1,
            "h": 1,
            "fit": "cover",
        })
        self.sync_contracts()
        self.approved_fixture()
        self.build(release=True)
        Image.new("RGB", (100, 100), "blue").save(photo)
        self.assertEqual(validate(self.project, mode="release", spec_only=True)["status"], "failed")

    def test_chart_value_change_detected(self):
        self.spec["slides"][0]["elements"] = [{"id": "S01-CHART", "type": "chart", "chartType": "bar", "x": 1, "y": 1, "w": 5, "h": 3, "data": [{"name": "数量", "labels": ["甲", "乙"], "values": [12, 18]}]}]
        self.save_spec()
        self.build()
        self.spec["slides"][0]["elements"][0]["data"][0]["values"][0] = 13
        self.save_spec()
        self.assertEqual(validate(self.project)["status"], "failed")

    def test_preview_requires_exact_ratio_and_real_png(self):
        path = self.project / "preview.png"
        for size in [(1664, 928), (1920, 1079), (1080, 1920)]:
            Image.new("RGB", size).save(path)
            self.assertTrue(image_errors(path))
        Image.new("RGB", (1920, 1080)).save(path)
        self.assertFalse(image_errors(path))
        Image.new("RGB", (1920, 1080)).save(path, format="JPEG")
        self.assertTrue(image_errors(path))
        path.write_bytes(b"not an image")
        self.assertTrue(image_errors(path))

    def test_preview_normalization_preserves_source_and_shape(self):
        source, output = self.project / "raw.png", self.project / "preview.png"
        Image.new("RGB", (400, 400), "red").save(source)
        before = digest(source)
        record = normalize(source, output, "pad", "#0000FF")
        self.assertEqual(record["original_size"], [400, 400])
        with Image.open(output) as image:
            self.assertEqual(image.size, (1920, 1080))
            self.assertEqual(image.getpixel((419, 540)), (0, 0, 255))
            self.assertEqual(image.getpixel((420, 540)), (255, 0, 0))
            self.assertEqual(image.getpixel((1499, 540)), (255, 0, 0))
            self.assertEqual(image.getpixel((1500, 540)), (0, 0, 255))
        self.assertEqual(digest(source), before)
        with self.assertRaises(ValueError):
            normalize(source, output, "strict")
        with self.assertRaises(ValueError):
            normalize(source, source)
        normalize(source, output, "crop")
        self.assertFalse(image_errors(output))

    def test_all_concept_pages_checked_before_approval(self):
        self.approved_fixture(through="1.3")
        self.generate_concept_set()
        Image.new("RGB", (640, 400)).save(self.project / "03_concepts/option-c/S01.png")
        result = self.workflow("approve", "concept", "--option", "a", "--evidence", "TEST FIXTURE ONLY", success=False)
        self.assertIn("1920x1080", result.stderr)
        self.assertFalse((self.project / "03_concepts/approval.json").exists())

    def test_full_preview_ratio_blocks_stage_and_release(self):
        self.approved_fixture(through="2.1")
        path = self.project / "04_full-preview/slides/S01.png"
        Image.new("RGB", (640, 400)).save(path)
        result = self.workflow("complete", "2.2", success=False)
        self.assertIn("1920x1080", result.stderr)
        self.assertTrue(stage_preview_errors(self.project, "2.2"))
        self.assertEqual(validate(self.project, mode="release", spec_only=True)["status"], "failed")

    def test_generation_jobs_require_stable_asset_ids(self):
        self.approved_fixture(through="1.3")
        write_json(
            self.project / "03_concepts/generation-jobs.json",
            {
                "jobs": [{
                    "id": "SQUARE",
                    "prompt": "SQUARE",
                    "output": "03_concepts/assets/GEN-501.png",
                    "intended_use": "测试缺失素材编号",
                    "factual_boundary": "不包含真实人物、地点或数据",
                }],
            },
        )
        result = self.run_python(
            "stages/21-concepts/scripts/run_generation.py",
            self.project,
            "--stage",
            "concepts",
            "--execute",
            success=False,
        )
        self.assertIn("asset_id", result.stderr)
        self.assertFalse((self.project / "03_concepts/assets/GEN-501.png").exists())

    def test_provider_square_output_is_kept_as_independent_asset(self):
        self.approved_fixture(through="1.3")
        write_json(
            self.project / "02_design/generation-jobs.json",
            {
                "jobs": [{
                    "id": "A",
                    "asset_id": "GEN-501",
                    "prompt": "SQUARE",
                    "output": "02_design/generated-assets/GEN-501.png",
                    "intended_use": "测试独立素材保留正方形比例",
                    "factual_boundary": "不包含真实人物、地点或数据",
                }],
            },
        )
        self.run_python("stages/21-concepts/scripts/run_generation.py", self.project, "--stage", "content", "--qwen-script", ROOT / "tests/mock_imagegen.py", "--execute")
        record = read_json(self.project / "02_design/generation-ledger.json")["jobs"]["A"]
        self.assertEqual(record["normalization"]["original_size"], [640, 640])
        self.assertEqual(record["normalization"]["output_size"], [640, 640])
        self.assertEqual(digest(self.project / record["raw_path"]), record["raw_sha256"])
        self.assertFalse(asset_image_errors(self.project / record["output"]))
        self.assertTrue(image_errors(self.project / record["output"]))

    def test_release_canvas_requires_widescreen(self):
        self.approved_fixture()
        self.spec["meta"] = {"layout": "CUSTOM", "width": 16, "height": 10}
        self.save_spec()
        report = validate(self.project, mode="release", spec_only=True)
        self.assertTrue(any("16:9" in error for error in report["errors"]))

    def test_reference_layout_regions_are_valid(self):
        layouts = read_json(ROOT / "stages/13-design/assets/reference-layouts.json")["layouts"]
        self.assertEqual(len({item["id"] for item in layouts}), 14)
        def check(value):
            if not isinstance(value, list):
                return
            if value and isinstance(value[0], list):
                for region in value:
                    check(region)
            else:
                x, y, w, h = value
                self.assertGreater(w, 0)
                self.assertGreater(h, 0)
                self.assertGreaterEqual(min(x, y), 0)
                self.assertLessEqual(x+w, 1.000001)
                self.assertLessEqual(y+h, 1.000001)
        for layout in layouts:
            for value in layout.values():
                check(value)

    def test_reference_categories_cover_every_indexed_page(self):
        index = read_json(ROOT / "stages/13-design/references/reference-index.json")
        taxonomy = read_json(ROOT / "stages/13-design/references/reference-categories.json")
        indexed_ids = {item["id"] for item in index["items"]}
        categorized_ids = [
            reference_id
            for category in taxonomy["categories"]
            for reference_id in category["reference_ids"]
        ]
        self.assertEqual(set(categorized_ids), indexed_ids)
        self.assertEqual(len(categorized_ids), len(set(categorized_ids)))
        self.assertEqual(len(taxonomy["categories"]), 14)
        for category in taxonomy["categories"]:
            self.assertEqual(category["id"], f"{category['page_type']}-{category['layout_id']}")
            self.assertIn(category["page_type"], taxonomy["taxonomy"]["page_types"])
            self.assertIn(category["layout_id"], taxonomy["taxonomy"]["layout_ids"])
            for reference_id in category["reference_ids"]:
                self.assertRegex(reference_id, r"^R[0-9]{3}$")

    def test_reference_category_selection_must_match_slide(self):
        content_path = self.project / "02_design/content.json"
        content = read_json(content_path)
        content["slides"][0]["reference_categories"] = ["toc-D01"]
        write_json(content_path, content)
        self.assertTrue(any("不一致" in error for error in design_errors(self.project)))
        content["slides"][0]["reference_categories"] = ["title-T01"]
        content["slides"][0]["reference_ids"] = ["R068"]
        write_json(content_path, content)
        self.assertTrue(any("不属于所选类别" in error for error in design_errors(self.project)))

    def test_sections_titles_must_match_toc_page(self):
        self.append_content_slide("S03", "研究背景与问题")
        self.sync_contracts()
        self.assertTrue(
            any("目录页条目" in error for error in design_errors(self.project))
        )
        content_path = self.project / "02_design/content.json"
        content = read_json(content_path)
        content["slides"][1]["texts"].append({
            "id": "S02-TOC-02",
            "text": content["sections"][0]["title"],
        })
        write_json(content_path, content)
        self.assertFalse(
            any("目录页条目" in error for error in design_errors(self.project))
        )

    def test_cutout_asset_bakes_transparent_png_and_registers(self):
        source = self.project / "00_intake/materials/photos/subject.png"
        subject = Image.new("RGB", (300, 300), "white")
        ImageDraw.Draw(subject).ellipse((60, 60, 240, 240), fill="#1F6F8B")
        subject.save(source)
        output = self.project / "05_reconstruction/rasters/decor-001.png"
        manifest = self.project / "05_reconstruction/assets.json"
        process = self.run_python(
            "shared/scripts/cutout_asset.py",
            self.project,
            source,
            output,
            "--source-id",
            "RECON-001",
            "--source-asset-id",
            "GEN-100",
            "--manifest",
            manifest,
            "--description",
            "测试抠图",
        )
        record = json.loads(process.stdout)
        self.assertEqual(record["sourceAssetId"], "GEN-100")
        self.assertGreater(record["transparentRatio"], 0.4)
        with Image.open(output) as baked:
            self.assertTrue(any(value > 0 for value in baked.convert("RGBA").getchannel("A").histogram()[:8]))
        stored = read_json(manifest)["assets"][0]
        self.assertEqual(stored["sourceId"], "RECON-001")
        flat = self.project / "00_intake/materials/photos/flat.png"
        Image.new("RGB", (200, 200), "#27776b").save(flat)
        self.run_python(
            "shared/scripts/cutout_asset.py",
            self.project,
            flat,
            self.project / "05_reconstruction/rasters/decor-002.png",
            "--source-id",
            "RECON-002",
            success=False,
        )
        self.run_python(
            "shared/scripts/cutout_asset.py",
            self.project,
            flat,
            self.project / "05_reconstruction/rasters/decor-003.png",
            "--source-id",
            "RECON-003",
            "--mask",
            "hexagon",
            "--no-cutout",
        )

    def test_project_lock_blocks_parallel_writers(self):
        self.approved_fixture(through="2.1")
        report = self.project / "00_intake/materials/reports/report.txt"
        lock = self.project / "workflow.lock"
        write_json(lock, {"pid": 4242, "at": datetime.now(timezone.utc).isoformat()})
        process = self.workflow(
            "material",
            "--id",
            "OTHER-002",
            "--path",
            str(report),
            "--kind",
            "other",
            success=False,
        )
        self.assertIn("workflow.lock", process.stdout + process.stderr)
        self.assertTrue(lock.is_file())
        write_json(lock, {"pid": 4242, "at": "2020-01-01T00:00:00+00:00"})
        self.workflow(
            "material",
            "--id",
            "OTHER-002",
            "--path",
            str(report),
            "--kind",
            "other",
        )
        self.assertFalse(lock.is_file())

    def test_await_is_limited_to_stop_points(self):
        self.sync_contracts()
        result = self.workflow(
            "await", "3.1", "--notes", "TEST FIXTURE ONLY", success=False
        )
        self.assertIn("不是停机点", result.stderr)
        self.assertIn("2.2", result.stderr)

    def test_stop_point_stage_requires_the_pause(self):
        self.sync_contracts()
        self.configure_mock_provider()
        self.workflow("approve", "requirements", "--evidence", "TEST FIXTURE ONLY")
        rejected = self.workflow("complete", "1.1", success=False)
        self.assertIn("停机点", rejected.stderr)
        self.assertIn("await", rejected.stderr)
        self.workflow("await", "1.1", "--notes", "TEST FIXTURE ONLY")
        self.workflow("complete", "1.1")

    def test_stop_point_command_reports_progress(self):
        self.sync_contracts()
        self.configure_mock_provider()
        mid = self.workflow("stop-point", success=False)
        self.assertIn("不得结束任务进程", mid.stderr)
        self.assertIn("1.1", mid.stderr)
        self.workflow("await", "1.1", "--notes", "TEST FIXTURE ONLY")
        parked = self.workflow("stop-point")
        self.assertIn("1.1", parked.stdout)
        self.assertIn("停机点", parked.stdout)
        self.workflow("approve", "requirements", "--evidence", "TEST FIXTURE ONLY")
        self.workflow("complete", "1.1")
        moving = self.workflow("stop-point", success=False)
        self.assertIn("1.2", moving.stderr)

    def test_content_stage_needs_plan_and_landscape_assets(self):
        self.sync_contracts()
        self.configure_mock_provider()
        self.workflow("await", "1.1", "--notes", "TEST FIXTURE ONLY")
        self.workflow("approve", "requirements", "--evidence", "TEST FIXTURE ONLY")
        self.workflow("complete", "1.1")

        rejected = self.workflow("complete", "1.2", success=False)
        self.assertIn("缺少内容清单", rejected.stderr)

        self.generate_content_assets()
        self.workflow("complete", "1.2")

    def test_hero_image_subject_sits_on_the_right(self):
        content = (ROOT / "stages/12-content/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("封面大图的构图要求必须写进提示词", content)
        self.assertIn("画面主体放在**右侧**", content)
        self.assertIn("左侧约 40%–50% 保持干净", content)

        for relative in (
            "SKILL.md",
            "stages/13-design/references/style-guide.md",
            "stages/13-design/assets/design-spec.md",
            "shared/artifact-contract.md",
            "shared/preview-contract.md",
        ):
            doc = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("主体偏右、左侧干净", doc, relative)

    def test_candidates_must_cover_every_design_direction(self):
        self.approved_fixture(through="1.1")
        self.generate_content_assets()
        registry_path = self.project / "02_design/generated-assets.json"
        registry = read_json(registry_path)

        for asset in registry["assets"]:
            asset.pop("styleId", None)
        write_json(registry_path, registry)
        rejected = self.workflow("complete", "1.2", success=False)
        self.assertIn("styleId", rejected.stderr)

        self.generate_content_assets()
        self.workflow("complete", "1.2")

        registry = read_json(registry_path)
        registry["assets"] = [
            asset for asset in registry["assets"] if asset["styleId"] != "b"
        ]
        write_json(registry_path, registry)
        rejected = self.workflow("complete", "1.2", success=False)
        self.assertIn("设计方向 b", rejected.stderr)

        self.generate_content_assets()
        self.workflow("complete", "1.2")

    def test_design_spec_needs_final_copy_and_block_grading(self):
        self.approved_fixture(through="1.2")
        spec = self.project / "02_design/design-spec.md"
        text = spec.read_text(encoding="utf-8")
        self.workflow("await", "1.3", "--notes", "TEST FIXTURE ONLY")

        spec.write_text(text.replace("上屏文案（最终文字）", "上屏文案"), encoding="utf-8")
        rejected = self.workflow("complete", "1.3", success=False)
        self.assertIn("上屏文案（最终文字）", rejected.stderr)

        spec.write_text(text.replace("分块方式", "分块"), encoding="utf-8")
        rejected = self.workflow("complete", "1.3", success=False)
        self.assertIn("分块方式", rejected.stderr)

        spec.write_text(
            text.replace("- **准确标题：** 测试内容", "- **准确标题：** 待填写", 1),
            encoding="utf-8",
        )
        rejected = self.workflow("complete", "1.3", success=False)
        self.assertIn("待填写", rejected.stderr)

        spec.write_text(text, encoding="utf-8")
        self.workflow("complete", "1.3")

    def test_edge_feather_defaults_are_generous(self):
        sys.path.insert(0, str(ROOT / "shared/scripts"))
        from asset_cutout import edge_transform

        transform = edge_transform({"type": "asset", "id": "X", "edge": {"mode": "feather"}})
        self.assertGreaterEqual(transform["feather"], 32)
        self.assertGreaterEqual(transform["radius"], 0.18)
        self.assertEqual(sorted(transform["edges"]), ["bottom", "left", "right", "top"])

    def test_thanks_page_is_optional_and_gated(self):
        self.sync_contracts()
        content_path = self.project / "02_design/content.json"
        content = read_json(content_path)
        content["include_thanks"] = True
        write_json(content_path, content)
        failures = design_errors(self.project)
        self.assertTrue(any("致谢页" in item for item in failures), failures)

        content["slides"].append({
            "id": "S09",
            "page_type": "thanks",
            "layout_id": "T01",
            "reference_ids": ["R058"],
            "reference_categories": ["title-T01"],
            "title": "致谢",
            "texts": [{"id": "S09-TITLE-01", "text": "致谢"}],
            "materials": [],
        })
        content["progress_bar"]["exclude_page_types"].append("thanks")
        write_json(content_path, content)
        intent_path = self.project / "02_design/image-intent-plan.json"
        intent = read_json(intent_path)
        intent["slides"].append({"id": "S09", "images": []})
        write_json(intent_path, intent)
        claim_path = self.project / "02_design/claim-map.json"
        claim = read_json(claim_path)
        claim["slides"].append({"id": "S09", "claims": []})
        write_json(claim_path, claim)
        self.assertEqual(design_errors(self.project), [])

    def test_environment_reports_font_inventory(self):
        self.run_python(
            "stages/00-init/scripts/check_environment.py",
            "--node",
            NODE,
            "--project",
            self.project,
            "--font",
            "Microsoft YaHei",
            success=(os.name == "nt"),
        )
        report = read_json(self.project / "00_intake/font-report.json")
        self.assertIn("families", report)
        self.assertIn("Microsoft YaHei", report["families"])
        self.run_python(
            "stages/00-init/scripts/check_environment.py",
            "--project",
            self.project,
            "--font",
            "NoSuchFontFamily",
            success=False,
        )

    def test_generation_prompt_scope_stays_light(self):
        scope = (ROOT / "stages/13-design/references/gen-prompt-scope.md").read_text(encoding="utf-8")
        for item in ("排版要求", "内容要求", "元素图", "图形元素", "风格与颜色限定"):
            self.assertIn(item, scope)
        self.assertIn("不要写进提示词", scope)
        for forbidden in ("检查码", "规则编号", "阈值"):
            self.assertIn(forbidden, scope)

        concepts = (ROOT / "stages/21-concepts/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("gen-prompt-scope.md", concepts)
        self.assertIn("不必展开整段风格规范", concepts)

        full = (ROOT / "stages/22-full-preview/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("gen-prompt-scope.md", full)
        self.assertIn("风格与颜色限定", full)

        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("阈值、检查码、规则编号", skill)

    def test_content_layouts_and_split_hints_are_aligned(self):
        """内容页八种版式（content-page.md）与参考库、分块词表必须对齐。"""
        references = ROOT / "stages/13-design/references"
        categories = read_json(references / "reference-categories.json")["categories"]
        content = {
            category["layout_id"]: category
            for category in categories
            if category["page_type"] == "content"
        }
        self.assertEqual(
            sorted(content), ["C01", "C02", "C03", "C04", "C05", "C06", "C07", "C08"]
        )
        menu = (references / "content-page.md").read_text(encoding="utf-8")
        for layout_id, category in content.items():
            hint = (category.get("split_hint") or "").strip()
            self.assertTrue(hint, layout_id)
            self.assertIn(layout_id, menu)
            self.assertIn(hint, menu, layout_id)
        for name in (
            "斜切", "弧线", "扇形", "同心圆", "波浪", "金字塔",
            "圆形放射", "左圆右栏", "六边形", "横带", "四宫格",
        ):
            self.assertIn(name, menu)
        self.assertIn("编号就是参考库的编号", menu)

    def test_special_split_methods_are_documented(self):
        splits = (ROOT / "stages/13-design/references/layout-splits.md").read_text(encoding="utf-8")
        for name in (
            "斜切分块",
            "弧线分块",
            "扇形分块",
            "同心圆分块",
            "波浪形分块",
            "金字塔形分块",
            "圆形分块（放射）",
            "左圆右栏分块",
            "横带分块（中间通栏）",
            "六边形分块（蜂窝）",
        ):
            self.assertIn(name, splits)
        self.assertIn("一半以上的正文页要用特殊分块，内容合适时越多越好", splits)
        self.assertIn("横带分块与四宫格分块不算特殊分块", splits)

        template = (ROOT / "stages/13-design/assets/design-spec.md").read_text(encoding="utf-8")
        self.assertIn("layout-splits.md", template)
        self.assertIn("斜切分块、弧线分块、扇形分块、同心圆分块、波浪形分块、金字塔形分块", template)

        for name in ("扇形分块", "同心圆分块", "波浪形分块", "金字塔形分块", "左圆右栏分块"):
            self.assertIn(name, splits)

        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("分块参考图", skill)

        design = (ROOT / "stages/13-design/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("特殊分块", design)

    def test_half_the_body_pages_need_special_splits(self):
        import re

        self.append_content_slide_with_toc("S03", "研究背景与问题")
        self.append_content_slide_with_toc("S04", "关键结论与证据")
        self.sync_contracts()
        self.assertEqual(
            [e for e in design_errors(self.project) if "特殊分块" in e], []
        )

        # 把所有正文页的分块方式改成常规分块 → 特殊分块不足
        spec = self.project / "02_design/design-spec.md"
        text = spec.read_text(encoding="utf-8")
        content = read_json(self.project / "02_design/content.json")
        content_ids = {
            slide["id"] for slide in content["slides"] if slide["page_type"] == "content"
        }
        lines = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("| S"):
                cells = [cell.strip() for cell in stripped.strip("|").split("|")]
                if cells and cells[0] in content_ids:
                    cells[1] = "上下分块"
                    line = "| " + " | ".join(cells) + " |"
            lines.append(line)
        spec.write_text("\n".join(lines) + "\n", encoding="utf-8")
        errors = [e for e in design_errors(self.project) if "特殊分块" in e]
        self.assertTrue(any("特殊分块页面不足" in e for e in errors), errors)

        # 一半（不是"多于一半"）不算通过：3 页正文里只有 1 页特殊分块 → 拒绝
        self.append_content_slide_with_toc("S05", "方法概览")
        self.sync_contracts()
        spec = self.project / "02_design/design-spec.md"
        text = spec.read_text(encoding="utf-8")
        patched = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("| S"):
                cells = [cell.strip() for cell in stripped.strip("|").split("|")]
                if cells and cells[0] in {"S04", "S05"}:
                    cells[1] = "上下分块"
                    line = "| " + " | ".join(cells) + " |"
            patched.append(line)
        spec.write_text("\n".join(patched) + "\n", encoding="utf-8")
        errors = [e for e in design_errors(self.project) if "特殊分块" in e]
        self.assertTrue(any("至少需要 2 页" in e for e in errors), errors)

        # 2/3 页用特殊分块（66%）→ 通过
        patched = []
        for line in spec.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("| S"):
                cells = [cell.strip() for cell in stripped.strip("|").split("|")]
                if cells and cells[0] == "S04":
                    cells[1] = "左右分块＋同心圆分块"
                    line = "| " + " | ".join(cells) + " |"
            patched.append(line)
        spec.write_text("\n".join(patched) + "\n", encoding="utf-8")
        self.assertEqual(
            [e for e in design_errors(self.project) if "特殊分块" in e], []
        )

        # 完全没有按页填写分块表 → 也要提示
        spec.write_text(
            "\n".join(
                line
                for line in text.splitlines()
                if not line.strip().startswith("| S")
            )
            + "\n",
            encoding="utf-8",
        )
        errors = [e for e in design_errors(self.project) if "特殊分块" in e]
        self.assertTrue(any("还没有按页填写分块方式" in e for e in errors), errors)

    def test_split_reference_images_ship_with_the_skill(self):
        folder = ROOT / "shared/references/splits"
        index = read_json(folder / "index.json")
        names = [entry["name"] for entry in index["splits"]]
        self.assertEqual(
            names,
            [
                "斜切", "弧线", "扇形", "同心圆", "波浪", "金字塔",
                "圆形放射", "左圆右栏", "六边形",
            ],
        )
        self.assertEqual(names, list(SPECIAL_SPLITS))
        macros = [entry["name"] for entry in index["macro"]]
        self.assertIn("四宫格（错位）", macros)
        self.assertIn("横带", macros)
        files = []
        for entry in index["splits"] + index["macro"]:
            self.assertTrue(entry["default"] in entry["files"], entry["id"])
            self.assertTrue(entry["form"].strip(), entry["id"])
            self.assertTrue(entry["prompt"].strip(), entry["id"])
            for name in entry["files"]:
                path = folder / name
                self.assertTrue(path.is_file(), name)
                with Image.open(path) as opened:
                    self.assertGreaterEqual(opened.width, 800)
                    grey = opened.convert("L")
                    histogram = grey.histogram()
                    bright = sum(histogram[201:])
                    share = bright / (grey.width * grey.height)
                self.assertGreater(share, 0.7, f"{name} 应是线稿样例（大面积留白）")
                files.append(name)
        self.assertEqual(len(set(files)), 16)

        # 设计稿里的分块写法都要能匹配到条目（含别名与标签）
        for cell in (
            "左中右分块＋斜切分块",
            "上下分块＋圆弧分块",
            "圆形分块（放射）",
            "四宫格分块",
            "上下分块＋横带分块",
            "左右分块＋六边形分块（蜂窝）",
        ):
            self.assertTrue(split_entries(cell), cell)

        # 参考图只作分区参考：文档与索引都要写明不要照抄图上的线条
        self.assertIn("分区参考", index["usage"])
        self.assertIn("不要照抄", index["usage"])
        self.assertIn("色差", index["usage"])
        script = ROOT / "shared/scripts/prepare_split_references.py"
        self.assertTrue(script.is_file())
        skeleton = (ROOT / "shared/operations.md").read_text(encoding="utf-8")
        self.assertIn("prepare_split_references.py", skeleton)
        self.assertIn("shared/references/splits/", skeleton)
        self.assertIn("02_design/split-references.json", skeleton)
        splits_doc = (ROOT / "stages/13-design/references/layout-splits.md").read_text(encoding="utf-8")
        for name in (
            "diagonal-cut.png",
            "concentric-circles.png",
            "concentric-with-columns.png",
            "left-disc-right-band.png",
            "band-row.png",
            "honeycomb.png",
            "offset-grid.png",
        ):
            self.assertIn(name, splits_doc)
        for relative in ("SKILL.md", "shared/operations.md", "shared/artifact-contract.md"):
            doc = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("split-references", doc, relative)
        for relative in (
            "SKILL.md",
            "shared/operations.md",
            "stages/13-design/references/layout-splits.md",
            "stages/13-design/assets/design-spec.md",
        ):
            doc = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("分区示意", doc, relative)
            self.assertIn("不要照抄", doc, relative)

    def test_rework_uses_image_to_image(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("被退回或需要修改的图必须用图生图改原图", skill)
        self.assertIn("不得重新用文生图从头生成", skill)
        concepts = (ROOT / "stages/21-concepts/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("被退回或需要修改的整页预览必须用图生图改原图", concepts)
        full = (ROOT / "stages/22-full-preview/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("被退回的页必须用图生图改原图", full)
        contract = (ROOT / "shared/preview-contract.md").read_text(encoding="utf-8")
        self.assertIn("必须用图生图改原图", contract)
        artifact = (ROOT / "shared/artifact-contract.md").read_text(encoding="utf-8")
        self.assertIn("一律用图生图改原图", artifact)

    def test_boxed_text_must_be_centered_and_fit(self):
        self.build()
        slide = self.spec["slides"][1]
        text = slide["elements"][0]
        slide["elements"].append({
            "id": "S02-BOX-01",
            "type": "shape",
            "shape": "roundRect",
            "x": round(text["x"] - 0.2, 3),
            "y": round(text["y"] - 0.1, 3),
            "w": round(text["w"] + 0.4, 3),
            "h": round(text["h"] + 0.2, 3),
            "fill": {"color": "EDF2F4"},
            "line": {"color": "CBD5DB"},
        })
        write_json(self.spec_path, self.spec)

        errors = spec_errors(self.project, self.spec)
        self.assertTrue(any("水平居中" in item for item in errors), errors)
        text["align"] = "center"
        errors = spec_errors(self.project, self.spec)
        self.assertTrue(any("垂直居中" in item for item in errors), errors)
        text["valign"] = "middle"
        self.assertFalse(spec_errors(self.project, self.spec), spec_errors(self.project, self.spec))

        text["text"] = "很长的正文文字" * 20
        errors = spec_errors(self.project, self.spec)
        self.assertTrue(any("放不进文本框" in item for item in errors), errors)

    def test_element_inventory_precedes_the_rebuild(self):
        self.approved_fixture(through="2.2")
        inventory = self.project / "05_reconstruction/element-inventory.md"
        self.assertTrue(inventory.is_file())

        audit = (ROOT / "stages/31-element-audit/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("element-inventory.md", audit)
        self.assertIn("\u4e0d\u542b\u8ba1\u5212\u56fe\u7247\u7684\u5360\u4f4d\u5757", audit)
        self.assertIn("\u8ba1\u5212\u7684\u5206\u79bb\u65b9\u5f0f", audit)

        rebuild = (ROOT / "stages/32-asset-rebuild/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("element-inventory.md", rebuild)
        self.assertIn("\u9010\u4e2a\u8fd8\u539f", rebuild)
        self.assertIn("AI \u62a0\u56fe", rebuild)
        self.assertIn("\u539f\u751f\u5143\u7d20\u7ec4\u88c5", rebuild)

        build = (ROOT / "stages/33-build/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("\u9875\u9762\u7684\u80cc\u666f\u53ea\u80fd\u662f\u8fd9\u4e09\u5f20 AI \u5927\u56fe", build)
        contract = (ROOT / "shared/artifact-contract.md").read_text(encoding="utf-8")
        self.assertIn("element-inventory.md", contract)

        # \u7f3a\u5c11\u5143\u7d20\u8bc6\u522b\u6e05\u5355 \u2192 \u4e0d\u80fd\u5b8c\u6210 3.1
        inventory.unlink()
        rejected = self.workflow("complete", "3.1", success=False)
        self.assertIn("element-inventory.md", rejected.stderr)

    def test_boxed_shapes_and_lines_must_be_rebuilt(self):
        audit = (ROOT / "stages/31-element-audit/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("异形文本框与线条装饰一个都不能省略", audit)
        rebuild = (ROOT / "stages/32-asset-rebuild/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("异形文本框与线条装饰必须逐一还原，不得省略", rebuild)
        build = (ROOT / "stages/33-build/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("异形文本框与线条装饰一定要还原，不能省略", build)
        self.assertIn("不能出格", build)
        self.assertIn("align: \"center\"", build)

    def test_visual_review_also_checks_placeholder_ratio(self):
        """逐页看图时要顺带目测占位块比例（粗略检查，不是机检）。"""
        for rel in (
            "SKILL.md",
            "shared/operations.md",
            "shared/preview-contract.md",
            "stages/21-concepts/SKILL.md",
            "stages/22-full-preview/SKILL.md",
        ):
            document = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("目测", document, rel)
            self.assertIn("不是机检", document, rel)
            self.assertIn("占位块", document, rel)

    def test_preview_placeholders_keep_the_planned_ratio(self):
        self.install_test_photo()
        self.approved_fixture(through="2.1")
        manifest_path = self.project / "03_concepts/option-b/preview.json"
        manifest = read_json(manifest_path)
        page = next(item for item in manifest["pages"] if item["id"] == "S01")
        entry = next(
            item for item in page["placeholders"] if item["imageId"] == "S01-PHOTO-01"
        )
        original = copy.deepcopy(entry["box"])
        self.assertFalse(preview_pages_errors(self.project, "2.1", "b"))

        entry["box"]["h"] = round(entry["box"]["h"] * 0.5, 4)
        write_json(manifest_path, manifest)
        failures = preview_pages_errors(self.project, "2.1", "b")
        self.assertTrue(any("占位块比例" in item for item in failures), failures)

        entry["box"] = {**original, "x": round(original["x"] + 0.1, 4)}
        write_json(manifest_path, manifest)
        failures = preview_pages_errors(self.project, "2.1", "b")
        self.assertTrue(any("占位块位置与图片计划不一致" in item for item in failures), failures)

        entry["box"] = original
        page.pop("placeholders")
        write_json(manifest_path, manifest)
        failures = preview_pages_errors(self.project, "2.1", "b")
        self.assertTrue(any("没有登记" in item for item in failures), failures)

        page["placeholders"] = [{"imageId": "S01-PHOTO-01", "box": original}]
        write_json(manifest_path, manifest)

        # 预览提示词没有写占位块 → 拦下
        jobs_path = self.project / "03_concepts/generation-jobs.json"
        jobs = read_json(jobs_path)
        job = next(item for item in jobs["jobs"] if item["id"] == "CONCEPT-B-S01")
        self.assertIn("\u5360\u4f4d\u5757", job["prompt"])
        job["prompt"] = "CONCEPT S01 整页预览，按设计稿生成"
        write_json(jobs_path, jobs)
        failures = preview_pages_errors(self.project, "2.1", "b")
        self.assertTrue(any("没有写占位块" in item for item in failures), failures)

    def test_special_splits_must_vary_between_pages(self):
        self.append_content_slide_with_toc("S03", "分块变化测试页一")
        self.append_content_slide_with_toc("S04", "分块变化测试页二")
        self.append_content_slide_with_toc("S05", "分块变化测试页三")
        self.sync_contracts()
        self.assertEqual(
            [item for item in design_errors(self.project) if "完全一样" in item], []
        )

        spec = self.project / "02_design/design-spec.md"
        text = spec.read_text(encoding="utf-8")
        methods = {page_id: cell for page_id, cell in page_split_rows(text)}
        self.assertIn("斜切", methods["S03"])
        self.assertNotEqual(methods["S03"], methods["S05"])

        # 把 S05 的分块方式改成与 S03 完全一样 → 拒绝
        lines = []
        for line in text.splitlines():
            if line.strip().startswith("| S05 |"):
                cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
                cells[1] = methods["S03"]
                line = "| " + " | ".join(cells) + " |"
            lines.append(line)
        spec.write_text("\n".join(lines) + "\n", encoding="utf-8")
        failures = [item for item in design_errors(self.project) if "完全一样" in item]
        self.assertTrue(any("S03" in item and "S05" in item for item in failures), failures)

        # 文档口径
        splits = (ROOT / "stages/13-design/references/layout-splits.md").read_text(encoding="utf-8")
        self.assertIn("两页之间不要用完全一样的特殊分块方式", splits)
        template = (ROOT / "stages/13-design/assets/design-spec.md").read_text(encoding="utf-8")
        self.assertIn("两页之间不要用完全一样的特殊分块方式", template)
        design = (ROOT / "stages/13-design/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("两页之间不要用完全一样的特殊分块方式", design)
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("两页之间不要用完全一样的特殊分块方式", skill)
        operations = (ROOT / "shared/operations.md").read_text(encoding="utf-8")
        self.assertIn("两页之间不要用完全一样的特殊分块方式", operations)

    def test_stage_spec_library_is_read_per_step(self):
        operations = (ROOT / "shared/operations.md").read_text(encoding="utf-8")
        self.assertIn("规范库索引（按步骤）", operations)
        self.assertIn("每开始一个步骤，先读一遍该步骤", operations)
        for folder in (
            "00-init", "11-intake", "12-content", "13-design",
            "21-concepts", "22-full-preview", "31-element-audit", "32-asset-rebuild",
            "33-build", "40-speaker-script",
        ):
            doc = (ROOT / f"stages/{folder}/SKILL.md").read_text(encoding="utf-8")
            self.assertIn("开工前先读规范库", doc, folder)

    def test_dissect_and_rebuild_rules_are_documented(self):
        for folder in ("31-element-audit", "32-asset-rebuild", "33-build"):
            doc = (ROOT / f"stages/{folder}/SKILL.md").read_text(encoding="utf-8")
            self.assertIn("背景层先铺 AI 大图", doc, folder)
            self.assertIn("完全拆解元素", doc, folder)
            self.assertIn("渐变风格必须还原", doc, folder)
            self.assertIn("hero-image", doc, folder)
            self.assertIn("content-background", doc, folder)
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("背景层用阶段 1.2 的 AI 大图", skill)
        self.assertIn("装饰色块与线条一个都不能漏", skill)

    def test_pixel_diff_check_is_removed(self):
        self.assertFalse((ROOT / "stages/33-build/scripts/visual_match.py").exists())
        self.assertFalse((ROOT / "shared/schemas/visual-match.schema.json").exists())
        for relative in ("SKILL.md", "stages/33-build/SKILL.md", "shared/artifact-contract.md"):
            doc = (ROOT / relative).read_text(encoding="utf-8")
            self.assertNotIn("visual_match.py", doc, relative)
            self.assertNotIn("visual-match.json", doc, relative)
        operations = (ROOT / "shared/operations.md").read_text(encoding="utf-8")
        self.assertIn("不做自动逐像素比对", operations)
        self.assertNotIn("visual_match.py", operations)
        prepare = (ROOT / "stages/33-build/scripts/prepare_review.py").read_text(encoding="utf-8")
        self.assertNotIn("visual_match", prepare)
        self.assertIn("对照图", prepare)

    def test_band_row_keeps_references_without_counting_as_special(self):
        self.append_content_slide_with_toc("S03", "横带分块页")
        self.append_content_slide_with_toc("S04", "斜切分块页")
        self.append_content_slide_with_toc("S05", "弧线分块页")
        self.approved_fixture(through="1.3")
        spec = self.project / "02_design/design-spec.md"
        text = spec.read_text(encoding="utf-8")
        row = next(line for line in text.splitlines() if line.startswith("| S03 |"))
        cells = row.strip("|").split("|")
        cells[1] = " 上下分块＋横带分块（中间通栏） "
        band_cell = cells[1]
        text = text.replace(row, "|" + "|".join(cells) + "|")
        # 另外两页保持特殊分块，确保特殊分块比例仍然达标（横带不计入）
        row = next(line for line in text.splitlines() if line.startswith("| S04 |"))
        cells = row.strip("|").split("|")
        cells[1] = " 左中右分块＋斜切分块 "
        text = text.replace(row, "|" + "|".join(cells) + "|")
        row = next(line for line in text.splitlines() if line.startswith("| S05 |"))
        cells = row.strip("|").split("|")
        cells[1] = " 上下分块＋弧线分块（横向向上凸） "
        text = text.replace(row, "|" + "|".join(cells) + "|")
        spec.write_text(text, encoding="utf-8")

        kinds = {entry["name"]: entry["kind"] for entry in split_entries(band_cell)}
        self.assertEqual(kinds.get("横带"), "macro")
        self.assertEqual(
            [entry["name"] for entry in SPECIAL_SPLITS if entry == "横带"], []
        )
        self.assertEqual(
            [e for e in design_errors(self.project) if "特殊分块页面不足" in e], []
        )

        # 不算特殊分块，但仍要复制参考图并交给 AI
        self.run_python("shared/scripts/prepare_split_references.py", self.project)
        manifest = read_json(self.project / "02_design/split-references.json")
        page = next(item for item in manifest["pages"] if item["id"] == "S03")
        self.assertTrue(any("band-row" in item for item in page["references"]))

        self.generate_concept_set()
        self.assertEqual(preview_pages_errors(self.project, "2.1", "a"), [])
        jobs_path = self.project / "03_concepts/generation-jobs.json"
        record = read_json(jobs_path)
        job = next(item for item in record["jobs"] if item["id"] == "CONCEPT-A-S03")
        band = next(item for item in job["references"] if "band-row" in item)
        job["references"] = [item for item in job["references"] if item != band]
        write_json(jobs_path, record)
        failures = preview_pages_errors(self.project, "2.1", "a")
        self.assertTrue(any("没有把分块参考图交给 AI" in item for item in failures), failures)

    def test_preview_tasks_carry_split_references(self):
        self.append_content_slide_with_toc("S03", "分块参考图测试页")
        self.approved_fixture(through="1.3")
        self.generate_concept_set()
        self.assertEqual(preview_pages_errors(self.project, "2.1", "a"), [])

        manifest_path = self.project / "02_design/split-references.json"
        manifest = read_json(manifest_path)
        page = next(item for item in manifest["pages"] if item["id"] == "S03")
        reference = page["references"][0]
        self.assertIn("split-references", reference)
        jobs_path = self.project / "03_concepts/generation-jobs.json"
        jobs = read_json(jobs_path)
        job = next(item for item in jobs["jobs"] if item["id"] == "CONCEPT-A-S03")
        self.assertIn(reference, job["references"])

        # 任务里没有参考图 → 拒绝
        job["references"] = [item for item in job["references"] if item != reference]
        write_json(jobs_path, jobs)
        failures = preview_pages_errors(self.project, "2.1", "a")
        self.assertTrue(any("没有把分块参考图交给 AI" in item for item in failures), failures)

        # 参考图没复制进项目 → 拒绝
        job["references"] = [reference]
        write_json(jobs_path, jobs)
        copied = self.project / reference
        payload = copied.read_bytes()
        copied.unlink()
        failures = preview_pages_errors(self.project, "2.1", "a")
        self.assertTrue(any("参考图还没复制进项目" in item for item in failures), failures)
        copied.write_bytes(payload)

        # 清单缺失 → 拒绝
        manifest_path.unlink()
        failures = preview_pages_errors(self.project, "2.1", "a")
        self.assertTrue(any("缺少特殊分块参考图清单" in item for item in failures), failures)
        write_json(manifest_path, manifest)
        self.assertEqual(preview_pages_errors(self.project, "2.1", "a"), [])

    def test_preview_prompt_keeps_split_curves(self):
        self.append_content_slide_with_toc("S03", "分块形态提示词测试页")
        self.approved_fixture(through="1.3")
        self.generate_concept_set()
        jobs_path = self.project / "03_concepts/generation-jobs.json"
        record = read_json(jobs_path)
        job = next(item for item in record["jobs"] if item["id"] == "CONCEPT-B-S03")
        original = job["prompt"]
        self.assertIn("斜切", original)

        # 没写分块方式 → 拒绝
        job["prompt"] = "CONCEPT-B S03 whole-page preview，文本框按设计稿，no watermark"
        write_json(jobs_path, record)
        failures = preview_pages_errors(self.project, "2.1", "b")
        self.assertTrue(any("没有写明特殊分块" in item for item in failures), failures)

        # 只写名字、没有形态 → 拒绝
        job["prompt"] = original.replace(
            "按设计稿的方向、走向与弯曲程度，", ""
        )
        write_json(jobs_path, record)
        failures = preview_pages_errors(self.project, "2.1", "b")
        self.assertTrue(any("没有写清它的形态" in item for item in failures), failures)

        # 没写"不要简化成直线" → 拒绝
        job["prompt"] = original.replace("，不要简化成直线", "")
        write_json(jobs_path, record)
        failures = preview_pages_errors(self.project, "2.1", "b")
        self.assertTrue(any("弧线与斜线不要直线化" in item for item in failures), failures)

        job["prompt"] = original
        write_json(jobs_path, record)
        self.assertEqual(preview_pages_errors(self.project, "2.1", "b"), [])

    def test_big_image_prompts_require_the_sixteen_by_nine_ratio(self):
        self.approved_fixture(through="1.2")
        jobs_path = self.project / "02_design/generation-jobs.json"
        record = read_json(jobs_path)
        big = [
            job for job in record["jobs"]
            if "\u5c01\u9762\u5927\u56fe" in (job.get("intended_use") or "")
        ]
        self.assertTrue(big)
        self.assertIn("16:9", big[0]["prompt"])
        for job in record["jobs"]:
            purpose = job.get("intended_use") or ""
            if any(token in purpose for token in ("\u5c01\u9762\u5927\u56fe", "\u80cc\u666f\u5e95\u56fe", "\u76ee\u5f55\u9875\u4e3b\u56fe")):
                self.assertIn("16:9", job["prompt"])

        # \u5927\u56fe\u63d0\u793a\u8bcd\u6ca1\u5199 16:9 \u2192 \u751f\u6210\u524d\u4e0e\u5b8c\u6210\u65f6\u90fd\u88ab\u62d2
        broken = [dict(job) for job in record["jobs"]]
        for job in broken:
            purpose = job.get("intended_use") or ""
            if any(token in purpose for token in ("\u5c01\u9762\u5927\u56fe", "\u80cc\u666f\u5e95\u56fe", "\u76ee\u5f55\u9875\u4e3b\u56fe")):
                job["prompt"] = "landscape cover art, theme aligned, no text"
        write_json(jobs_path, {"jobs": broken})
        failures = generation_jobs_errors(self.project, "1.2")
        self.assertTrue(any("\u6ca1\u6709\u5199\u660e\u6bd4\u4f8b 16:9" in item for item in failures), failures)

        rejected = self.run_python(
            "stages/21-concepts/scripts/run_generation.py",
            self.project,
            "--stage",
            "content",
            success=False,
        )
        self.assertIn("16:9", rejected.stderr)

        for rel in (
            "stages/12-content/SKILL.md",
            "shared/preview-contract.md",
            "shared/operations.md",
            "SKILL.md",
        ):
            document = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("16:9", document, rel)

    def test_logic_arrows_and_fixed_placeholder_ratio_reach_the_prompt(self):
        photo = self.project / "00_intake/materials/photos/ratio-lock.png"
        Image.new("RGB", (1600, 400), "#2F5D62").save(photo)
        self.register_material("PHOTO-001", photo, "photo")
        self.append_content_slide_with_toc("S03", "逻辑关系测试页")
        self.spec["slides"][-1]["elements"].append({
            "id": "S03-PHOTO-01",
            "type": "image",
            "sourceId": "PHOTO-001",
            "path": photo.relative_to(self.project).as_posix(),
            "x": 6.2,
            "y": 3.0,
            "w": 6.4,
            "h": 1.6,
            "fit": "cover",
            "altText": "逻辑关系测试照片",
        })
        self.save_spec()
        self.approved_fixture(through="1.3")

        spec_path = self.project / "02_design/design-spec.md"
        text = spec_path.read_text(encoding="utf-8")
        section = (
            "### S03：逻辑关系测试页\n"
            "- **文字层级与并列：** S03-TITLE-01 标题；S03-PHOTO-01 计划图片。\n"
            "- **页内逻辑关系（可选）：** 三步递进，用箭头把 S03-TITLE-01 指向 S03-PHOTO-01。\n"
            "- **排版分级：** 测试内容（文本框：圆角矩形；图像框：按原图比例；无图片）。\n"
        )
        spec_path.write_text(text + "\n" + section, encoding="utf-8")

        jobs_path = self.project / "03_concepts/generation-jobs.json"
        jobs = self.preview_jobs("2.1", "a")
        write_json(jobs_path, {"jobs": jobs})
        failures = preview_prompt_errors(self.project, "2.1")
        self.assertTrue(any("没有写页内逻辑关系" in item for item in failures), failures)
        self.assertFalse(any("占位框的宽高比不能改变" in item for item in failures), failures)

        # 设计稿只要求「按比例」，没写死不变：去掉提示词里的强调就会被拒
        job = next(item for item in jobs if item["id"] == "CONCEPT-A-S03")
        job["prompt"] = job["prompt"].replace("占位块比例不得改变（不拉伸、不变形），", "")
        write_json(jobs_path, {"jobs": jobs})
        failures = preview_prompt_errors(self.project, "2.1")
        self.assertTrue(any("占位框的宽高比不能改变" in item for item in failures), failures)

        # 补上箭头关系与比例强调后通过
        job["prompt"] += "；占位块比例不得改变（不拉伸、不变形）；页内逻辑关系：箭头从 S03-TITLE-01 指向 S03-PHOTO-01"
        write_json(jobs_path, {"jobs": jobs})
        self.assertEqual(preview_prompt_errors(self.project, "2.1"), [])

    def test_preview_prompt_self_check_before_generation(self):
        self.approved_fixture(through="1.3")
        jobs_path = self.project / "03_concepts/generation-jobs.json"
        jobs = self.preview_jobs("2.1", "a")
        write_json(jobs_path, {"jobs": jobs})
        self.assertEqual(preview_prompt_errors(self.project, "2.1"), [])

        # \u5c11\u4e86\u753b\u5e03\u6bd4\u4f8b\u3001\u98ce\u683c\u3001\u8fdb\u5ea6\u6761\u3001\u6587\u5b57\u4e0e\u6587\u672c\u6846\u5f62\u72b6 \u2192 \u81ea\u68c0\u62a6\u4e0b
        broken = [dict(job) for job in jobs]
        broken[0]["prompt"] = "CONCEPT-A S01 whole-page preview"
        write_json(jobs_path, {"jobs": broken})
        failures = preview_prompt_errors(self.project, "2.1")
        for marker in ("16:9", "\u98ce\u683c", "\u8fdb\u5ea6\u6761", "\u6ca1\u6709\u5199\u660e\u6587\u5b57", "\u6587\u672c\u6846\u5f62\u72b6"):
            self.assertTrue(any(marker in item for item in failures), failures)

        # \u751f\u6210\u811a\u672c\u5728\u51fa\u56fe\u524d\u5148\u81ea\u68c0\uff1a\u574f\u63d0\u793a\u8bcd\u76f4\u63a5\u62d2\u7edd
        rejected = self.run_python(
            "stages/21-concepts/scripts/run_generation.py",
            self.project,
            "--stage",
            "concepts",
            success=False,
        )
        self.assertIn("16:9", rejected.stderr)
        self.assertIn("\u98ce\u683c", rejected.stderr)

        # \u8981\u6c42\u6324\u6210\u4e00\u6574\u53e5\uff08\u6ca1\u6709\u5206\u70b9\uff09\u4e5f\u62d2\u7edd
        flattened = [dict(job) for job in jobs]
        flattened[0]["prompt"] = " ".join(flattened[0]["prompt"].splitlines())
        write_json(jobs_path, {"jobs": flattened})
        failures = preview_prompt_errors(self.project, "2.1")
        self.assertTrue(any("\u8981\u6309\u5206\u70b9\u5199" in item for item in failures), failures)

        write_json(jobs_path, {"jobs": jobs})
        self.assertEqual(preview_prompt_errors(self.project, "2.1"), [])
        self.run_python(
            "stages/21-concepts/scripts/run_generation.py",
            self.project,
            "--stage",
            "concepts",
        )

        for rel, marker in (
            ("stages/21-concepts/SKILL.md", "\u751f\u6210\u524d\u81ea\u68c0"),
            ("stages/22-full-preview/SKILL.md", "\u751f\u6210\u524d\u81ea\u68c0"),
            ("stages/13-design/references/gen-prompt-scope.md", "\u5148\u81ea\u68c0\u518d\u51fa\u56fe"),
            ("shared/preview-contract.md", "\u751f\u6210\u4e4b\u524d"),
            ("shared/operations.md", "\u5148\u81ea\u68c0\u518d\u51fa\u56fe"),
            ("SKILL.md", "\u751f\u6210\u524d\u81ea\u68c0"),
        ):
            document = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn(marker, document, rel)

        for rel in (
            "stages/13-design/references/gen-prompt-scope.md",
            "stages/21-concepts/SKILL.md",
            "stages/22-full-preview/SKILL.md",
            "shared/preview-contract.md",
            "shared/operations.md",
            "SKILL.md",
        ):
            document = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("\u6309\u5206\u70b9\u5206\u884c\u5199", document, rel)

    def test_same_style_preview_keeps_the_big_image_palette(self):
        self.approved_fixture(through="2.1")
        self.assertFalse(preview_pages_errors(self.project, "2.1", "b"))

        jobs_path = self.project / "03_concepts/generation-jobs.json"
        record = read_json(jobs_path)
        job = next(item for item in record["jobs"] if item["id"] == "CONCEPT-B-S01")
        original = job["prompt"]
        self.assertIn("\u540c\u4e00\u5957\u914d\u8272", original)

        # \u63d0\u793a\u8bcd\u6ca1\u5199\u540c\u98ce\u683c\u914d\u8272 \u2192 \u751f\u6210\u524d\u81ea\u68c0\u62a6\u4e0b
        job["prompt"] = original.replace(
            "\u80cc\u666f\u4e0e\u88c5\u9970\u7528\u4e0e\u6240\u7ed9\u5927\u56fe\u76f8\u8fd1\u7684\u989c\u8272\uff08\u540c\u4e00\u5957\u914d\u8272\uff09\u3002", ""
        )
        write_json(jobs_path, record)
        failures = preview_prompt_errors(self.project, "2.1")
        self.assertTrue(any("\u6ca1\u6709\u5199\u540c\u98ce\u683c\u914d\u8272\u8981\u6c42" in item for item in failures), failures)
        job["prompt"] = original
        write_json(jobs_path, record)

        # \u9884\u89c8\u56fe\u6539\u6210\u5b8c\u5168\u4e0d\u540c\u7684\u914d\u8272 \u2192 \u62d2\u7edd
        manifest_path = self.project / "03_concepts/option-b/preview.json"
        manifest = read_json(manifest_path)
        page = manifest["pages"][0]
        slide = self.project / page["file"]
        Image.new("RGB", (1920, 1080), "#0B1E3A").save(slide)
        page["sha256"] = digest(slide)
        write_json(manifest_path, manifest)
        ledger_path = self.project / "03_concepts/generation-ledger.json"
        ledger = read_json(ledger_path)
        ledger["jobs"][page["jobId"]]["sha256"] = page["sha256"]
        write_json(ledger_path, ledger)
        failures = preview_pages_errors(self.project, "2.1", "b")
        self.assertTrue(any("\u914d\u8272\u76f8\u5dee\u8fc7\u5927" in item for item in failures), failures)

        for rel in (
            "stages/13-design/references/gen-prompt-scope.md",
            "stages/21-concepts/SKILL.md",
            "stages/22-full-preview/SKILL.md",
            "shared/preview-contract.md",
            "shared/operations.md",
            "shared/artifact-contract.md",
            "SKILL.md",
        ):
            document = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("\u540c\u4e00\u5957\u914d\u8272", document, rel)

    def test_preview_prompt_forbids_geometry_and_font_sizes_keeps_image_ratios(self):
        photo = self.project / "00_intake/materials/photos/preview-ratio.png"
        Image.new("RGB", (1600, 400), "#2F5D62").save(photo)
        self.register_material("PHOTO-001", photo, "photo")
        self.append_content_slide_with_toc("S03", "字号与图片比例测试页")
        self.spec["slides"][-1]["elements"].append({
            "id": "S03-PHOTO-01",
            "type": "image",
            "sourceId": "PHOTO-001",
            "path": photo.relative_to(self.project).as_posix(),
            "x": 6.2,
            "y": 3.0,
            "w": 6.4,
            "h": 1.6,
            "fit": "cover",
            "altText": "字号与图片比例测试照片",
        })
        self.save_spec()
        self.approved_fixture(through="1.3")
        self.generate_concept_set()
        self.assertEqual(preview_pages_errors(self.project, "2.1", "a"), [])

        jobs_path = self.project / "03_concepts/generation-jobs.json"
        record = read_json(jobs_path)
        job = next(item for item in record["jobs"] if item["id"] == "CONCEPT-A-S03")
        original = job["prompt"]
        self.assertIn("4:1", original)
        self.assertNotIn("字号要求", original)
        # A conforming prompt passes; each prohibited instruction fails preflight.
        for directive, reason in (("正文36px，字号18pt。", "字号"),
                                  ("文本框大小600×140px。", "文本框大小"),
                                  ("标题x=0.05,y=0.12。", "元素具体位置")):
            job["prompt"] = original + "\n" + directive
            write_json(jobs_path, record)
            failures = preview_prompt_errors(self.project, "2.1")
            self.assertTrue(any("禁写信息" in item and reason in item for item in failures), failures)

        # 没写图片位比例 → 拒绝
        job["prompt"] = original.replace("图片位比例 4:1", "")
        write_json(jobs_path, record)
        failures = preview_pages_errors(self.project, "2.1", "a")
        self.assertTrue(any("没有写明 S03-PHOTO-01 的图片位比例" in item for item in failures), failures)

        job["prompt"] = original
        write_json(jobs_path, record)
        self.assertEqual(preview_pages_errors(self.project, "2.1", "a"), [])

    def test_prompt_policy_does_not_reject_canvas_ratios_or_scientific_content(self):
        self.assertEqual(preview_prompt_forbidden_details(
            "16:9（1920×1080）；图片位比例4:1；左区证据、右区解释；正文：半衰期250±22.1 min。"), [])
        self.assertEqual(preview_prompt_forbidden_details(
            "内容：字号识别实验；分区关系照设计稿。", ["字号识别实验"]), [])
        for directive in ("字体大小24磅", "fontSize=36", "文本框宽600", "左上96,289px", "上边距20px"):
            self.assertTrue(preview_prompt_forbidden_details(directive), directive)

    def test_toc_page_has_two_layout_options(self):
        toc = (ROOT / "stages/13-design/references/toc-page.md").read_text(encoding="utf-8")
        self.assertIn("D01 左列目录", toc)
        self.assertIn("D02 多行多列横向排布", toc)
        self.assertIn("两种版式", toc)
        self.assertNotIn("D08", toc)

        template = (ROOT / "stages/13-design/assets/design-spec.md").read_text(encoding="utf-8")
        self.assertIn("D01 左列目录", template)
        self.assertIn("D02 多行多列横向排布", template)

        guide = (ROOT / "stages/13-design/references/style-guide.md").read_text(encoding="utf-8")
        self.assertIn("目录页版式二选一", guide)

    def test_preview_assets_map_one_to_one_with_pages(self):
        scope = (ROOT / "stages/13-design/references/gen-prompt-scope.md").read_text(encoding="utf-8")
        for item in (
            "标题页→该方向的标题图 `hero-image`",
            "目录页→该方向的目录图 `toc-image`",
            "其他页（内容页／致谢页）→该方向的背景图 `content-background`",
            "每页只给这一张",
        ):
            self.assertIn(item, scope)

        concepts = (ROOT / "stages/21-concepts/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("标题页→该方向的标题图 `hero-image`", concepts)
        self.assertIn("其他页→该方向的背景图 `content-background`", concepts)

        full = (ROOT / "stages/22-full-preview/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("标题页＝标题图 `hero-image`", full)
        self.assertIn("其他页＝背景图 `content-background`", full)

        guide = (ROOT / "stages/13-design/references/style-guide.md").read_text(encoding="utf-8")
        self.assertIn("每页只带一张对应基础元素图", guide)

        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("标题页＝`hero-image`", skill)
        self.assertIn("其他页＝`content-background`", skill)

    def test_representative_content_page_is_not_pinned_to_the_first(self):
        self.append_content_slide_with_toc("S03", "研究背景与问题")
        self.append_content_slide_with_toc("S04", "关键结论与证据")
        self.approved_fixture(through="1.3")
        jobs = self.preview_jobs("2.1", "a")
        content = read_json(self.project / "02_design/content.json")
        page_type = {slide["id"]: slide["page_type"] for slide in content["slides"]}
        toc = next(sid for sid, kind in page_type.items() if kind == "toc")
        picked = "S04"  # 任选一页内容页（不是第一个内容页 S03）
        wanted = ["S01", toc, picked]
        jobs = [job for job in jobs if job["id"].rpartition("-")[2] in wanted]
        if not any(job["id"].endswith(picked) for job in jobs):
            jobs.append(
                self.preview_job(
                    self.preview_context("2.1", "a"), "2.1", "a", picked, 390
                )
            )
        self.run_generation(
            "03_concepts", "03_concepts/generation-jobs.json", jobs, "concepts"
        )
        pages = []
        for job in jobs:
            page_id = job["id"].rpartition("-")[2]
            relative, sha = self.place_preview_page("2.1", "a", page_id, job["asset_id"])
            entry = {
                "id": page_id,
                "file": relative,
                "jobId": job["id"],
                "sha256": sha,
                "promptSummary": f"按设计稿 {page_id} 生成整页预览",
            }
            pages.append(entry)
        manifest_path = self.project / "03_concepts/option-a/preview.json"
        write_json(manifest_path, {
            "version": 1,
            "stage": "2.1",
            "option": "a",
            "styleDirection": "方向 a",
            "pages": pages,
        })
        self.assertEqual(preview_pages_errors(self.project, "2.1", "a"), [])

        # 少了内容页代表页 → 报错
        write_json(manifest_path, {
            "version": 1,
            "stage": "2.1",
            "option": "a",
            "styleDirection": "方向 a",
            "pages": [page for page in pages if page["id"] != picked],
        })
        failures = preview_pages_errors(self.project, "2.1", "a")
        self.assertTrue(any("至少要有一页内容页代表页" in item for item in failures), failures)

    def test_design_spec_carries_requirements_but_no_norm_chapters(self):
        self.approved_fixture(through="1.2")
        spec = self.project / "02_design/design-spec.md"
        text = spec.read_text(encoding="utf-8")
        required = (
            "## 全篇叙述逻辑链",
            "## 目录要求",
            "## 顶部进度条要求",
            "## 页面分块要求",
            "## 文本框、要点拆分与装饰色系要求",
            "## 背景底图与内容页补图要求",
            "## 待补充材料",
        )
        for heading in required:
            self.assertIn(heading, text)
        for retired in ("## 装饰词汇与圆弧圆环要求", "## 封面与目录页大图要求"):
            self.assertNotIn(retired, text)

        guide = (ROOT / "stages/13-design/references/style-guide.md").read_text(encoding="utf-8")
        self.assertIn("AI 素材、封面大图与背景底图要求", guide)
        for item in (
            "封面整体大图占画布不少于 20%",
            "content-background",
            "每页只带一张对应基础元素图",
            "hero-image",
            "toc-image",
            "抠出边缘或套几何遮罩",
        ):
            self.assertIn(item, guide)

        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("都由 AI 生成素材承担", skill)
        self.assertIn("背景底图与内容页补图", skill)
        self.assertNotIn("《封面与目录页大图要求》", skill)

        self.workflow("await", "1.3", "--notes", "TEST FIXTURE ONLY")
        for heading in required:
            spec.write_text(text.replace(heading, "## 被删掉的小节"), encoding="utf-8")
            rejected = self.workflow("complete", "1.3", success=False)
            self.assertIn("设计稿必须提供独立章节", rejected.stderr)
            self.assertIn(heading.lstrip("# "), rejected.stderr)

        spec.write_text(text, encoding="utf-8")
        self.workflow("complete", "1.3")

    def test_design_spec_states_a_box_shape_for_every_text(self):
        self.approved_fixture(through="1.2")
        spec = self.project / "02_design/design-spec.md"
        text = spec.read_text(encoding="utf-8")
        self.workflow("await", "1.3", "--notes", "TEST FIXTURE ONLY")
        self.assertIn("文本框：形状＋大致大小", text)
        self.assertIn("无文本框：用线条托住", text)
        self.assertIn("同一组并列的每一段都必须用同一种文本框形状", text)
        self.assertIn("图像框：位置＋比例", text)
        self.workflow("complete", "1.3")

        self.approved_fixture(through="1.2")
        spec = self.project / "02_design/design-spec.md"
        text = spec.read_text(encoding="utf-8")
        self.workflow("await", "1.3", "--notes", "TEST FIXTURE ONLY")
        plan_start = text.index("## 逐页规划")
        stripped = (
            text[:plan_start]
            + text[plan_start:].replace("文本框：", "框：").replace("文本框形状", "形状")
        )
        spec.write_text(stripped, encoding="utf-8")
        rejected = self.workflow("complete", "1.3", success=False)
        self.assertIn("文本框形状", rejected.stderr)

    def test_prompt_scope_treats_text_as_a_box_reference(self):
        scope = (ROOT / "stages/13-design/references/gen-prompt-scope.md").read_text(encoding="utf-8")
        self.assertIn("禁止写文本框大小、字号、元素具体位置", scope)
        self.assertIn("不要求模型逐字排印", scope)
        self.assertIn("并列文本段落要统一", scope)

        concepts = (ROOT / "stages/21-concepts/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("禁止写文本框大小、字号、元素具体位置", concepts)

        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("禁止写文本框大小、字号、元素具体位置", skill)
        self.assertIn("分别说明对应的文本框形状", skill)

    def test_design_spec_must_carry_element_geometry(self):
        self.approved_fixture(through="1.2")
        spec = self.project / "02_design/design-spec.md"
        text = spec.read_text(encoding="utf-8")
        self.assertIn("- **元素位置与大小：**", text)
        self.workflow("await", "1.3", "--notes", "TEST FIXTURE ONLY")

        spec.write_text(
            text.replace("- **元素位置与大小：**", "- **元素位置：**"),
            encoding="utf-8",
        )
        rejected = self.workflow("complete", "1.3", success=False)
        self.assertIn("元素位置与大小", rejected.stderr)

        spec.write_text(text, encoding="utf-8")
        self.workflow("complete", "1.3")

    def test_design_spec_pages_must_declare_their_boxes(self):
        self.approved_fixture(through="1.2")
        spec = self.project / "02_design/design-spec.md"
        text = spec.read_text(encoding="utf-8")
        self.assertIn("文本框：", text)
        self.workflow("await", "1.3", "--notes", "TEST FIXTURE ONLY")

        stripped = text.replace("文本框：", "文本框").replace("无文本框", "无框")
        spec.write_text(stripped, encoding="utf-8")
        rejected = self.workflow("complete", "1.3", success=False)
        self.assertIn("文本框", rejected.stderr)

        spec.write_text(text, encoding="utf-8")
        self.workflow("complete", "1.3")

    def test_block_subtitles_are_declared_in_grading(self):
        template = (ROOT / "stages/13-design/assets/design-spec.md").read_text(encoding="utf-8")
        self.assertIn("- **分块的分标题**", template)
        self.assertIn("；分标题：（一段文字）", template)
        self.assertIn("Sxx-SECTION-01", template)
        self.assertIn("分块同一行", template)
        self.assertIn("`；分标题：（一段文字）`", template)

        design = (ROOT / "stages/13-design/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("；分标题：（一段文字）", design)
        self.assertIn("Sxx-SECTION-01", design)

        template = (ROOT / "stages/13-design/assets/design-spec.md").read_text(encoding="utf-8")
        self.assertIn("分块的分标题", template)
        self.assertIn("；分标题：", template)
        preview = (ROOT / "stages/22-full-preview/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("分块", preview)

        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("；分标题：", skill)
        self.assertIn("没写的不许自己加", skill)

        operations = (ROOT / "shared/operations.md").read_text(encoding="utf-8")
        self.assertIn("；分标题：（文字）", operations)

        # 分标题只靠设计稿与提示词约束，不做机检：写了分标题不该产生新错误。
        self.append_content_slide_with_toc("S03", "分标题测试页")
        self.sync_contracts()
        self.assertEqual([e for e in design_errors(self.project) if "分标题" in e], [])
        spec = self.project / "02_design/design-spec.md"
        text = spec.read_text(encoding="utf-8")
        marker = "- **排版分级：** 测试内容（文本框：圆角矩形；图像框：按原图比例；无图片）。"
        self.assertIn(marker, text)
        spec.write_text(
            text.replace(
                marker,
                marker + " 分块上方标注分标题：方法概览。",
            ),
            encoding="utf-8",
        )
        self.assertEqual([e for e in design_errors(self.project) if "分标题" in e], [])
        self.assertFalse(
            any("文本框" in error for error in design_errors(self.project)
                if error.startswith("S03")),
            design_errors(self.project),
        )

    def test_parallel_structures_become_nested_lists(self):
        template = (ROOT / "stages/13-design/assets/design-spec.md").read_text(encoding="utf-8")
        self.assertIn("列表套列表", template)
        self.assertIn("再降一级", template)
        self.assertIn(">例四", template)
        self.assertIn("此条内部还有并列，再降一级：", template)
        example = template.split(">例四", 1)[1].split("\n分块方式可组合", 1)[0]
        self.assertEqual(example.count("**并列文本**"), 5)
        self.assertIn("      1. **并列文本**", example)
        self.assertIn("         1. **并列文本**", example)
        self.assertIn("**一段文本里只要有并列结构**", template)
        self.assertIn("拆成列表", template)

        design = (ROOT / "stages/13-design/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("列表套列表", design)
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("列表套列表", skill)
        self.assertIn("拆成列表", skill)
        operations = (ROOT / "shared/operations.md").read_text(encoding="utf-8")
        self.assertIn("列表套列表", operations)

    def test_preview_prompt_must_carry_the_text_boxes(self):
        self.approved_fixture(through="1.3")
        jobs = self.preview_jobs("2.1", "a")
        self.run_generation(
            "03_concepts", "03_concepts/generation-jobs.json", jobs, "concepts"
        )
        for job in jobs:
            job["prompt"] = (
                job["prompt"]
                .replace("text boxes with the design shapes", "text content only")
                .replace("文本框形状", "形状")
                .replace("文本框", "文字块")
            )
        write_json(
            self.project / "03_concepts/generation-jobs.json", {"jobs": jobs}
        )
        pages = []
        for job in jobs:
            page_id = job["id"].rpartition("-")[2]
            relative, sha = self.place_preview_page("2.1", "a", page_id, job["asset_id"])
            pages.append({
                "id": page_id,
                "file": relative,
                "jobId": job["id"],
                "sha256": sha,
                "promptSummary": f"按设计稿 {page_id} 生成整页预览",
            })
        write_json(self.project / "03_concepts/option-a/preview.json", {
            "version": 1,
            "stage": "2.1",
            "option": "a",
            "styleDirection": "方向 a",
            "pages": pages,
        })
        failures = preview_pages_errors(self.project, "2.1", "a")
        self.assertTrue(any("没有写文本框" in item for item in failures), failures)

    def test_preview_page_must_match_its_generation_record(self):
        self.approved_fixture(through="2.1")
        manifest_path = self.project / "04_full-preview/previews.json"
        self.generate_full_preview()
        manifest = read_json(manifest_path)
        slides = self.project / "04_full-preview/slides"
        Image.new("RGB", (1920, 1080), "#123456").save(slides / "S01.png")
        manifest["pages"][0]["sha256"] = digest(slides / "S01.png")
        write_json(manifest_path, manifest)
        failures = preview_pages_errors(self.project, "2.2")
        self.assertTrue(any("插入后的页面被修改" in item for item in failures), failures)

    def test_full_preview_must_cover_every_page(self):
        self.approved_fixture(through="2.1")
        self.generate_full_preview()
        manifest_path = self.project / "04_full-preview/previews.json"
        manifest = read_json(manifest_path)
        manifest["pages"] = manifest["pages"][:-1]
        write_json(manifest_path, manifest)
        failures = preview_pages_errors(self.project, "2.2")
        self.assertTrue(any("覆盖全部定稿页面" in item for item in failures), failures)

    def test_full_preview_needs_the_locked_style_constraints(self):
        self.approved_fixture(through="2.1")
        self.generate_full_preview()
        manifest_path = self.project / "04_full-preview/previews.json"
        manifest = read_json(manifest_path)
        manifest.pop("styleConstraints")
        write_json(manifest_path, manifest)
        failures = preview_pages_errors(self.project, "2.2")
        self.assertTrue(any("styleConstraints" in item for item in failures), failures)

    def test_speaker_script_stage_is_optional_and_gated(self):
        self.approved_fixture(through="2.2")
        failures = speaker_script_errors(self.project)
        self.assertTrue(any("应跳过" in item for item in failures), failures)
        content_path = self.project / "02_design/content.json"
        content = read_json(content_path)
        content["include_speaker_script"] = True
        write_json(content_path, content)
        failures = speaker_script_errors(self.project)
        self.assertTrue(any("缺少演讲稿" in item for item in failures), failures)
        content_slides = [slide["id"] for slide in content["slides"]]
        notes_dir = self.project / "08_speaker-notes"
        notes_dir.mkdir(parents=True, exist_ok=True)
        write_json(notes_dir / "notes.json", {
            "version": 1,
            "pages": [{"id": slide_id, "notes": "太短"} for slide_id in content_slides],
        })
        (notes_dir / "speaker-script.md").write_text("# 演讲稿\n", encoding="utf-8")
        failures = speaker_script_errors(self.project)
        self.assertTrue(any("太短" in item for item in failures), failures)
        write_json(notes_dir / "notes.json", {
            "version": 1,
            "pages": [
                {"id": slide["id"], "notes": f"这一页讲{slide['title']}：先点出结论，再补一句数据来源、样本量与口径限制，最后给出下一步安排。"}
                for slide in content["slides"]
            ],
        })
        script = ["# 演讲稿", ""]
        for slide in content["slides"]:
            script += [f"## {slide['id']} {slide['title']}", "讲述要点。", ""]
        (notes_dir / "speaker-script.md").write_text("\n".join(script), encoding="utf-8")
        self.assertEqual(speaker_script_errors(self.project), [])

    def test_plain_textbox_builds_without_inner_decoration(self):
        self.spec["slides"][1]["elements"] = [
            {
                "id": "S02-PANEL-01", "type": "shape", "shape": "roundRect",
                "x": 1, "y": 2, "w": 5, "h": 2,
                "fill": {"color": "DCE8E6"}, "z": 1,
            },
            {
                "id": "S02-TITLE-01", "type": "text", "text": "无装饰的文本框",
                "x": 1, "y": 2, "w": 5, "h": 2,
                "fontFace": "Microsoft YaHei", "fontSize": 28,
                "color": "18212B", "align": "center", "valign": "middle", "z": 2,
            },
        ]
        self.build()
        result = validate(self.project)
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual(result["slides"][1]["native_texts"], 1)

    def test_thanks_reuses_candidate_background_without_extra_generation(self):
        assets = [
            {"id": f"GEN-{index}-{kind}", "styleId": style, "kind": kind}
            for index, style in enumerate(("a", "b", "c"))
            for kind in ("hero-image", "content-background")
        ]
        self.assertEqual(candidate_style_errors(assets, include_thanks=True), [])
        errors = candidate_style_errors(assets, include_toc=True, include_thanks=True)
        self.assertEqual(len(errors), 3)
        self.assertTrue(all("toc-image" in message for message in errors), errors)
        assets += [{"id": f"GEN-TOC-{style}", "styleId": style, "kind": "toc-image"}
                   for style in ("a", "b", "c")]
        self.assertEqual(candidate_style_errors(assets, include_toc=True, include_thanks=True), [])

    def test_thanks_palette_uses_background_and_ignores_legacy_thanks_candidate(self):
        directory = self.project / "02_design/generated-assets"
        directory.mkdir(exist_ok=True)
        background = directory / "background.png"
        legacy_thanks = directory / "thanks.png"
        preview = directory / "preview.png"
        Image.new("RGB", (1920, 1080), "#228833").save(background)
        Image.new("RGB", (1920, 1080), "#EE3322").save(legacy_thanks)
        Image.new("RGB", (1920, 1080), "#228833").save(preview)
        write_json(self.project / "02_design/generated-assets.json", {"version": 1, "assets": [
            {"id": "GEN-BG", "kind": "content-background", "styleId": "a",
             "path": background.relative_to(self.project).as_posix()},
            {"id": "GEN-THANKS", "kind": "thanks-image", "styleId": "a",
             "path": legacy_thanks.relative_to(self.project).as_posix()},
        ]})
        content_path = self.project / "02_design/content.json"
        content = read_json(content_path)
        content["slides"].append({"id": "S09", "page_type": "thanks"})
        write_json(content_path, content)
        pages = [{"id": "S09", "file": preview.relative_to(self.project).as_posix()}]
        self.assertEqual(preview_palette_errors(self.project, "2.1", "a", pages), [])
        Image.new("RGB", (1920, 1080), "#EE3322").save(preview)
        self.assertTrue(preview_palette_errors(self.project, "2.1", "a", pages))

    def record_photo_position_polish(self):
        element = next(item for item in self.spec["slides"][0]["elements"]
                       if item["id"] == "S01-PHOTO-01")
        self.spec["meta"]["layoutAdjustmentAuthorization"] = "TEST FIXTURE: 用户允许成品美化时自由调整元素位置"
        element["layoutAdjustment"] = {
            "from": {"x": element["x"], "y": element["y"], "z": element.get("z", 0)},
            "reason": "调整图文间距与视觉重心",
        }
        element["x"] -= .25
        element["y"] += .2
        element["z"] = element.get("z", 0) + 2
        return element

    def test_position_polish_preserves_preview_approval_and_passes_release(self):
        self.install_test_photo()
        self.approved_fixture()
        self.build(release=True)
        self.write_render(matched=True)
        self.run_python("stages/33-build/scripts/prepare_review.py", self.project)
        self.sign_review()
        original_plan_hash = digest(self.project / "02_design/image-plan.json")
        self.record_photo_position_polish()
        self.save_spec()
        self.assertEqual(spec_errors(self.project, self.spec, release=True), [])
        self.assertEqual(approval_errors(self.project, "preview"), [])
        self.build(release=True)
        self.assertEqual(validate(self.project, mode="release")["status"], "failed")
        self.write_render(matched=False)
        self.run_python("stages/33-build/scripts/prepare_review.py", self.project)
        self.assertFalse(read_json(self.project / "07_delivery/qa-review.json")["pages"][0]["visual"])
        self.sign_review()
        review_path = self.project / "07_delivery/qa-review.json"
        review = read_json(review_path)
        page = review["pages"][0]
        page["preview_match"] = False
        page["deviations"] = [{
            "type": "layout_adjustment", "region": {"x": 0, "y": 0, "w": 1, "h": 1},
            "severity": "minor", "expected": "初始预览位置", "actual": "图片向左并向下移动",
            "reason": "改善图文间距", "evidence": "07_delivery/review/S01-compare.png",
            "approved_by": "TEST FIXTURE: 用户既有位置美化授权",
            "approved_at": "2026-10-04T03:00:00Z",
        }]
        write_json(review_path, review)
        self.assertEqual(validate(self.project, mode="release")["status"], "passed")
        self.assertEqual(digest(self.project / "02_design/image-plan.json"), original_plan_hash)
        self.workflow("complete", "3.3")

    def test_position_polish_does_not_bypass_source_size_or_baseline_checks(self):
        self.install_test_photo()
        element = self.record_photo_position_polish()
        self.assertEqual(spec_errors(self.project, self.spec), [])
        for key, value in (("sourceId", "PHOTO-CHANGED"), ("path", "missing.png"),
                           ("fit", "contain"), ("w", element["w"] + .3)):
            original = element[key]
            element[key] = value
            self.assertTrue(spec_errors(self.project, self.spec), key)
            element[key] = original
        element["layoutAdjustment"]["from"]["x"] += 1
        self.assertTrue(any("位置调整起点" in item for item in spec_errors(self.project, self.spec)))
        element["layoutAdjustment"]["from"]["x"] -= 1
        self.spec["meta"].pop("layoutAdjustmentAuthorization")
        self.assertTrue(any("缺少 meta.layoutAdjustmentAuthorization" in item
                            for item in spec_errors(self.project, self.spec)))

    def test_position_polish_supports_text_and_shape_objects(self):
        self.spec["meta"]["layoutAdjustmentAuthorization"] = "TEST FIXTURE: 工作流第 28 条"
        self.spec["slides"][1]["elements"].append({
            "id": "S02-DECOR", "type": "shape", "shape": "rect",
            "x": 1, "y": 2, "w": 1, "h": .2, "fill": {"color": "228833"},
        })
        for element in self.spec["slides"][1]["elements"]:
            element["layoutAdjustment"] = {"from": {"x": element["x"], "y": element["y"]},
                                           "reason": "改善对齐与间距"}
            element["x"] += .3
        self.save_spec()
        self.build()
        self.assertEqual(validate(self.project)["status"], "passed")

    def test_speaker_script_stage_waits_for_the_finished_deck(self):
        self.approved_fixture(through="2.2")
        content_path = self.project / "02_design/content.json"
        content = read_json(content_path)
        content["include_speaker_script"] = True
        write_json(content_path, content)
        rejected = self.workflow("complete", "4", success=False)
        self.assertIn("阶段 3.1 未完成", rejected.stderr)

    @staticmethod
    def curved_boundary_mask():
        # A curved left edge: only peripheral corners are removed.
        edge = [{"x": .18 * (2 * i / 32 - 1) ** 2, "y": i / 32}
                for i in range(32, -1, -1)]
        return {"points": [{"x": .18, "y": 0}, {"x": 1, "y": 0},
                            {"x": 1, "y": 1}] + edge,
                "boundary": "弧形分块左侧边缘", "reason": "裁去非关键角落以贴合弧线",
                "protectsContent": True}

    def test_boundary_mask_preview_preserves_original_and_detects_tampering(self):
        source = self.install_test_photo()
        original_hash = digest(source)
        provider = self.project / "04_full-preview/provider-test.png"
        Image.new("RGB", (1920, 1080), "blue").save(provider)
        plan = read_json(self.project / "02_design/image-plan.json")["slides"][0]
        image = plan["images"][0]
        image["boundaryMask"] = self.curved_boundary_mask()
        item = {"imageId": image["id"], "sourceId": image["sourceId"],
                "path": image["path"], "sha256": original_hash, "box": image["box"],
                "fit": "contain", "boundaryMask": copy.deepcopy(image["boundaryMask"])}
        result = compose(self.project, provider.relative_to(self.project), [item])
        out = self.project / "04_full-preview/masked-test.png"
        result.save(out)
        page = {"id": "S01", "file": out.relative_to(self.project).as_posix(),
                "providerFile": provider.relative_to(self.project).as_posix(),
                "providerSha256": digest(provider), "originals": [item]}
        self.assertEqual(insertion_errors(self.project, page, plan), [])
        x, y = round(image["box"]["x"] * 1920), round(image["box"]["y"] * 1080)
        w, h = round(image["box"]["w"] * 1920), round(image["box"]["h"] * 1080)
        self.assertEqual(result.getpixel((x + 2, y + 2)), (0, 0, 255))
        self.assertEqual(result.getpixel((x + w // 2, y + h // 2)), (255, 0, 0))
        self.assertEqual(digest(source), original_hash)
        item["boundaryMask"]["points"][0]["x"] = .3
        self.assertTrue(any("裁切轮廓" in error for error in insertion_errors(self.project, page, plan)))
        for point in ({"x": float("nan"), "y": 0}, {"x": 1.1, "y": 0}):
            bad = self.curved_boundary_mask()
            bad["points"][0] = point
            with self.assertRaises(ValueError):
                boundary_mask(bad, (100, 100))

    def test_boundary_mask_build_keeps_source_and_native_text(self):
        source = self.install_test_photo()
        original_hash = digest(source)
        element = self.record_photo_position_polish()
        element["layoutAdjustment"]["from"]["boundaryMask"] = None
        element["boundaryMask"] = self.curved_boundary_mask()
        plan_hash = digest(self.project / "02_design/image-plan.json")
        self.save_spec()
        self.assertEqual(spec_errors(self.project, self.spec), [])
        self.build()
        manifest = read_json(self.project / "07_delivery/build-manifest.json")
        asset = next(item for item in manifest["assets"] if item["id"] == element["id"])
        self.assertEqual(asset["source_sha256"], original_hash)
        self.assertEqual(asset["boundaryMask"], element["boundaryMask"])
        found = False
        with zipfile.ZipFile(self.project / "07_delivery/deck.pptx") as archive:
            for name in archive.namelist():
                if not name.startswith("ppt/media/") or not name.endswith(".png"):
                    continue
                payload = archive.read(name)
                import hashlib
                if hashlib.sha256(payload).hexdigest() == asset["embedded_sha256"]:
                    with Image.open(io.BytesIO(payload)) as bitmap:
                        self.assertEqual(bitmap.mode, "RGBA")
                        self.assertEqual(bitmap.getpixel((2, 2))[3], 0)
                        self.assertEqual(bitmap.getpixel((bitmap.width // 2, bitmap.height // 2)), (255, 0, 0, 255))
                        found = True
            text = archive.read("ppt/slides/slide1.xml").decode("utf-8")
            self.assertIn("图片计划测试", text)
            self.assertIn("<a:t>", text)
        self.assertTrue(found)
        self.assertEqual(digest(source), original_hash)
        self.assertEqual(digest(self.project / "02_design/image-plan.json"), plan_hash)
        self.assertEqual(validate(self.project)["status"], "passed")
        element["layoutAdjustment"]["from"].pop("boundaryMask")
        self.assertTrue(any("boundaryMask" in error for error in spec_errors(self.project, self.spec)))

    def test_boundary_mask_is_inserted_before_full_preview_approval(self):
        self.install_test_photo()
        element = next(e for e in self.spec["slides"][0]["elements"] if e["type"] == "image")
        mask = self.curved_boundary_mask()
        element["boundaryMask"] = mask
        self.save_spec()
        path = self.project / "02_design/image-plan.json"
        plan = read_json(path)
        plan["slides"][0]["images"][0]["boundaryMask"] = mask
        write_json(path, plan)
        self.approved_fixture(through="2.2")
        pages = read_json(self.project / "04_full-preview/previews.json")["pages"]
        self.assertEqual(pages[0]["originals"][0]["boundaryMask"], mask)
        self.assertEqual(approval_errors(self.project, "preview"), [])
        self.assertEqual(spec_errors(self.project, self.spec), [])
        # JSON member order has no effect on the planned clipping contour.
        element["boundaryMask"] = {key: mask[key] for key in reversed(mask)}
        self.save_spec()
        self.build()

    def test_preview_prompt_requires_adaptive_height_without_numeric_dimensions(self):
        clause = "文本框的高度要与实际文本高度相匹配，仅保留适量内边距，避免框内大片留白。"
        self.assertTrue(preview_prompt_height_matches_content(clause))
        self.assertEqual(preview_prompt_forbidden_details(clause), [])
        self.assertFalse(preview_prompt_height_matches_content("文本框颜色协调，避免框内大片留白。"))
        self.assertFalse(preview_prompt_height_matches_content(clause, [clause]))
        self.assertTrue(preview_prompt_forbidden_details("文本框高度=140px"))
        self.approved_fixture(through="1.3")
        self.generate_concept_set()
        self.assertEqual(preview_prompt_errors(self.project, "2.1"), [])
        path = self.project / "03_concepts/generation-jobs.json"
        jobs = read_json(path)
        jobs["jobs"][0]["prompt"] = jobs["jobs"][0]["prompt"].replace(
            "文本框高度与实际文本高度匹配，仅保留适量内边距，避免框内大片留白。", "")
        write_json(path, jobs)
        self.assertTrue(any("缺少框高适配要求" in error for error in preview_prompt_errors(self.project, "2.1")))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--node", default="node")
    args, remaining = parser.parse_known_args()
    NODE = args.node
    unittest.main(argv=[sys.argv[0], *remaining], verbosity=2)
