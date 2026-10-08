#!/usr/bin/env python3
"""Pair final renders with approved previews and prepare pending human QA."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageOps, ImageStat

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared/scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from workflow_lib import approval_errors, check_hashes, digest, now, read_json, write_json
from dependency_scope import review_dependencies


def _archive(paths, output):
    archive = output / "history" / now().replace(":", "-")
    archive.mkdir(parents=True, exist_ok=True)
    for path in paths:
        if path.is_file():
            (archive / path.name).write_bytes(path.read_bytes())


def _previous_pages(path):
    if not path.is_file():
        return {}, {}
    try:
        previous = read_json(path)
    except (OSError, ValueError, TypeError):
        return {}, {}
    indexed = {
        page.get("id"): page
        for page in previous.get("pages", [])
        if isinstance(page, dict) and page.get("id")
    }
    return indexed, previous


def _normalized_review(page, render_hash, reused):
    review_mode = page.get("review_mode")
    if review_mode not in {"pending", "manual", "assisted"}:
        review_mode = "manual" if page.get("human_signed") else "pending"
    confidence = page.get("confidence")
    deviations = page.get("deviations")
    return {
        "id": page["id"],
        "render_sha256": render_hash,
        "visual": page.get("visual") is True,
        "content": page.get("content") is True,
        "photos": page.get("photos") is True,
        "editability": page.get("editability") is True,
        "preview_match": page.get("preview_match") is True,
        "review_mode": review_mode,
        "confidence": confidence if isinstance(confidence, (int, float)) else 0,
        "human_signed": page.get("human_signed") is True,
        "notes": page.get("notes", "复用同一渲染版本的既有审阅" if reused else "待逐页审阅"),
        "deviations": deviations if isinstance(deviations, list) else [],
    }


def prepare(project):
    project = Path(project).resolve()
    delivery = project / "07_delivery"
    render_path = delivery / "render-manifest.json"
    render = read_json(render_path)

    approval = approval_errors(project, "preview")
    if approval:
        raise ValueError("\n".join(approval))
    if render.get("pptx_sha256") != digest(delivery / "deck.pptx"):
        raise ValueError("渲染版本已失效，请先重新渲染")
    for page in render.get("pages", []):
        errors = check_hashes(project, {page["path"]: page["sha256"]})
        if errors:
            raise ValueError("\n".join(errors))

    previous_pages, previous_review = _previous_pages(delivery / "qa-review.json")
    output = delivery / "review"
    output.mkdir(parents=True, exist_ok=True)
    warnings = []
    thumbs = []
    review_pages = []
    manifest_pages = []
    reused_count = 0
    dependencies = review_dependencies(project)
    for page in render["pages"]:
        page_id = page["id"]
        preview_path = project / "04_full-preview/slides" / f"{page_id}.png"
        render_image_path = project / page["path"]
        actual = Image.open(render_image_path).convert("RGB")
        if max(ImageStat.Stat(actual).stddev) < 1:
            warnings.append(f"{page_id} 渲染疑似空白，必须核查")

        pair = Image.new("RGB", (1280, 420), "#e7e9ec")
        draw = ImageDraw.Draw(pair)
        draw.text((12, 8), f"{page_id} - APPROVED PREVIEW", fill="black")
        draw.text((652, 8), f"{page_id} - PPTX RENDER", fill="black")
        image = ImageOps.contain(Image.open(preview_path).convert("RGB"), (616, 370))
        pair.paste(image, (12, 38))
        image = ImageOps.contain(actual, (616, 370))
        pair.paste(image, (652, 38))
        compare_path = output / f"{page_id}-compare.png"
        pair.save(compare_path)
        thumbs.append(ImageOps.contain(actual, (400, 240)))

        previous = previous_pages.get(page_id)
        reused = bool(previous and previous.get("render_sha256") == page["sha256"]
                      and previous.get("dependency_sha256") == dependencies.get(page_id))
        if reused:
            reused_count += 1
            review = _normalized_review(previous, page["sha256"], True)
        else:
            review = {
                "id": page_id,
                "render_sha256": page["sha256"],
                "visual": False,
                "content": False,
                "photos": False,
                "editability": False,
                "preview_match": False,
                "review_mode": "pending",
                "confidence": 0,
                "human_signed": False,
                "notes": "待逐页审阅",
                "deviations": [],
            }
        review["dependency_sha256"] = dependencies[page_id]
        review_pages.append(review)
        manifest_pages.append({
            "id": page_id,
            "preview_path": preview_path.relative_to(project).as_posix(),
            "render_path": page["path"],
            "compare_path": compare_path.relative_to(project).as_posix(),
            "preview_sha256": digest(preview_path),
            "render_sha256": page["sha256"],
            "review_reused": reused,
        })

    sheet = Image.new("RGB", (1200, max(1, (len(thumbs) + 2) // 3) * 270), "#e7e9ec")
    draw = ImageDraw.Draw(sheet)
    for index, thumbnail in enumerate(thumbs):
        x, y = index % 3 * 400, index // 3 * 270
        sheet.paste(thumbnail, (x, y + 24))
        draw.text((x + 6, y + 5), review_pages[index]["id"], fill="black")
    sheet.save(output / "contact-sheet.png")

    qa_path = delivery / "qa-review.json"
    manifest_path = delivery / "review-manifest.json"
    _archive([qa_path, manifest_path], output)

    all_reused = reused_count == len(review_pages)
    qa = {
        "version": 1,
        "content_sha256": digest(project / "02_design/content.json"),
        "image_plan_sha256": digest(project / "02_design/image-plan.json"),
        "previews_sha256": digest(project / "04_full-preview/previews.json"),
        "pptx_package_sha256": digest(delivery / "deck.pptx"),
        "render_manifest_sha256": digest(render_path),
        "reviewer": previous_review.get("reviewer", "") if all_reused else "",
        "reviewed_at": previous_review.get("reviewed_at", "") if all_reused else "",
        "warnings": warnings,
        "pages": review_pages,
    }
    write_json(qa_path, qa)
    manifest = {
        "version": 1,
        "created_at": now(),
        "pptx_sha256": digest(delivery / "deck.pptx"),
        "image_plan_sha256": digest(project / "02_design/image-plan.json"),
        "previews_sha256": digest(project / "04_full-preview/previews.json"),
        "preview_approval_sha256": digest(project / "04_full-preview/approval.json"),
        "render_manifest_sha256": digest(render_path),
        "pages": manifest_pages,
    }
    write_json(manifest_path, manifest)
    print(
        f"已生成 {len(review_pages)} 页对照图（已批准预览 vs PPTX 渲染）与待审阅记录；"
        f"复用 {reused_count} 页既有审阅。没有自动比对、也没有自动批准任何页面，"
        "请逐页对照后人工填写 qa-review.json。"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir")
    args = parser.parse_args()
    try:
        prepare(Path(args.project_dir).resolve())
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        sys.exit(1)
