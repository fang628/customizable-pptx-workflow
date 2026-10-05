#!/usr/bin/env python3
"""Bake an AI asset into a transparent PNG for the editable PPTX."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from PIL import Image, ImageOps

from asset_cutout import border_color, cutout_foreground
from shape_masks import apply_mask, make_mask
from workflow_lib import digest, read_json, replace_file, write_json

MASKS = [
    "none",
    "circle",
    "ellipse",
    "capsule",
    "bubble",
    "rounded-rectangle",
    "hexagon",
    "trapezoid",
    "parallelogram",
]


def _project_path(project, value):
    path = Path(value)
    return path.resolve() if path.is_absolute() else (project / path).resolve()


def _hex(value):
    if value is None:
        return None
    text = str(value).lstrip("#")
    if len(text) != 6:
        raise ValueError("background 必须是 #RRGGBB")
    try:
        int(text, 16)
    except ValueError:
        raise ValueError("background 必须是 #RRGGBB") from None
    return f"#{text.upper()}"


def bake(
    project,
    source_path,
    output_path,
    source_id,
    mask="none",
    cutout=True,
    tolerance=28,
    feather=2,
    background=None,
    manifest_path=None,
    description="",
    source_asset_id=None,
):
    project = Path(project).resolve()
    source_path = _project_path(project, source_path)
    output_path = _project_path(project, output_path)
    if not output_path.is_relative_to(project):
        raise ValueError("抠图输出必须位于项目目录内")
    if output_path.suffix.lower() != ".png":
        raise ValueError("抠图输出必须是 PNG")
    if source_path == output_path:
        raise ValueError("不能覆盖原始素材")
    if not source_path.is_file():
        raise ValueError(f"源素材不存在：{source_path}")
    if mask not in MASKS:
        raise ValueError(f"mask 必须是 {MASKS}")
    if not cutout and mask == "none":
        raise ValueError("必须至少使用边缘抠图或几何遮罩之一，否则仍是方形素材")
    background = _hex(background)
    if not 0 <= int(tolerance) <= 128:
        raise ValueError("tolerance 必须在 0 到 128 之间")
    if not 0 <= float(feather) <= 12:
        raise ValueError("feather 必须在 0 到 12 之间")

    with Image.open(source_path) as original:
        image = ImageOps.exif_transpose(original).convert("RGBA")
    source_size = list(image.size)
    detected = None
    if cutout:
        detected = "#%02X%02X%02X" % border_color(image)
        image = cutout_foreground(image, int(tolerance), float(feather), background)
    mask_name = mask if mask != "none" else None
    if mask_name:
        image = apply_mask(image, make_mask(mask_name, image.size))
    alpha = image.getchannel("A")
    histogram = alpha.histogram()
    transparent = sum(histogram[:250])
    total = image.width * image.height
    ratio = transparent / total if total else 0.0
    if ratio <= 0.0:
        raise ValueError(
            "抠图没有产生任何透明像素；请确认素材背景是纯色、或改用 --mask，"
            "避免方形素材直接进入画面"
        )
    if ratio >= 0.995:
        raise ValueError(
            f"抠图去掉了 {ratio:.0%} 的素材，几乎整张图都被抹掉："
            "素材主体颜色与背景过于接近，请换用带主体的素材，或改用 --mask 几何遮罩"
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(".tmp.png")
    image.save(temporary, format="PNG")
    replace_file(temporary, output_path)

    record = {
        "sourceId": source_id,
        "path": output_path.relative_to(project).as_posix(),
        "sha256": digest(output_path),
        "sourcePath": source_path.relative_to(project).as_posix()
        if source_path.is_relative_to(project)
        else str(source_path),
        "sourceSha256": digest(source_path),
        "sourceSize": source_size,
        "outputSize": list(image.size),
        "alphaMode": "edge-cutout" if cutout else "mask",
        "mask": mask,
        "cutout": {
            "enabled": bool(cutout),
            "tolerance": int(tolerance),
            "feather": float(feather),
            "background": background or detected,
        },
        "transparentRatio": round(ratio, 4),
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "description": description,
    }
    if source_asset_id:
        record["sourceAssetId"] = source_asset_id
    if manifest_path:
        manifest_path = _project_path(project, manifest_path)
        manifest = read_json(manifest_path) if manifest_path.exists() else {"assets": []}
        if not isinstance(manifest.get("assets"), list):
            raise ValueError("素材清单必须包含 assets 数组")
        manifest["assets"] = [
            item for item in manifest["assets"] if item.get("sourceId") != source_id
        ]
        manifest["assets"].append(record)
        write_json(manifest_path, manifest)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir")
    parser.add_argument("source")
    parser.add_argument("output")
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--source-asset-id")
    parser.add_argument("--mask", choices=MASKS, default="none")
    parser.add_argument("--no-cutout", action="store_true")
    parser.add_argument("--tolerance", type=int, default=28)
    parser.add_argument("--feather", type=float, default=2)
    parser.add_argument("--background")
    parser.add_argument("--manifest")
    parser.add_argument("--description", default="")
    args = parser.parse_args()
    project = Path(args.project_dir).resolve()
    result = bake(
        project,
        args.source,
        args.output,
        args.source_id,
        args.mask,
        not args.no_cutout,
        args.tolerance,
        args.feather,
        args.background,
        args.manifest,
        args.description,
        args.source_asset_id,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        sys.exit(1)
