#!/usr/bin/env python3
"""Deterministically crop an image with EXIF orientation and explicit units."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from PIL import Image, ImageOps

from workflow_lib import asset_path, digest, read_json, replace_file, write_json


def _number(value, name):
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} 必须是数值") from None
    if not 0 <= result <= 1:
        raise ValueError(f"{name} 必须在 0 到 1 之间")
    return result


def _project_path(project, value):
    path = Path(value)
    return path.resolve() if path.is_absolute() else (project / path).resolve()


def crop_asset(project, source_path, output_path, source_id, crop, background="#FFFFFF",
               focus=None, manifest_path=None, description="", alpha_mode="flatten",
               alpha_mask=None):
    source_path = _project_path(project, source_path)
    output_path = _project_path(project, output_path)
    if not output_path.is_relative_to(project):
        raise ValueError("裁剪输出必须位于项目目录内")
    if output_path.suffix.lower() != ".png":
        raise ValueError("裁剪输出必须是 PNG")
    if source_path.resolve() == output_path:
        raise ValueError("不能覆盖原始素材")
    if not source_path.is_file():
        raise ValueError(f"源素材不存在：{source_path}")
    if alpha_mode not in {"flatten", "keep", "mask"}:
        raise ValueError("alpha_mode 必须是 flatten、keep 或 mask")
    if alpha_mode == "mask" and not alpha_mask:
        raise ValueError("alpha_mode=mask 时必须提供 alpha_mask")
    if alpha_mode != "mask" and alpha_mask:
        raise ValueError("只有 alpha_mode=mask 时才能提供 alpha_mask")

    x = _number(crop.get("x"), "crop.x")
    y = _number(crop.get("y"), "crop.y")
    width = _number(crop.get("width"), "crop.width")
    height = _number(crop.get("height"), "crop.height")
    if width <= 0 or height <= 0:
        raise ValueError("裁剪宽高必须大于 0")
    if x + width > 1.0000001 or y + height > 1.0000001:
        raise ValueError("裁剪区域超出图像边界")
    if not isinstance(background, str) or len(background) != 7 or background[0] != "#":
        raise ValueError("background 必须是 #RRGGBB")
    try:
        int(background[1:], 16)
    except ValueError:
        raise ValueError("background 必须是 #RRGGBB") from None

    with Image.open(source_path) as original:
        oriented = ImageOps.exif_transpose(original).convert("RGBA")
    source_size = oriented.size
    left = round(x * source_size[0])
    top = round(y * source_size[1])
    right = max(left + 1, round((x + width) * source_size[0]))
    bottom = max(top + 1, round((y + height) * source_size[1]))
    if focus:
        focus_x = _number(focus.get("x"), "focus.x")
        focus_y = _number(focus.get("y"), "focus.y")
        left = round(focus_x * source_size[0] - (right - left) / 2)
        top = round(focus_y * source_size[1] - (bottom - top) / 2)
        left = max(0, min(source_size[0] - (right - left), left))
        top = max(0, min(source_size[1] - (bottom - top), top))
        right = left + max(1, round(width * source_size[0]))
        bottom = top + max(1, round(height * source_size[1]))

    cropped = oriented.crop((left, top, right, bottom))
    mask_path = None
    mask_hash = None
    if alpha_mode == "mask":
        mask_path = _project_path(project, alpha_mask)
        if not mask_path.is_file():
            raise ValueError(f"透明度蒙版不存在：{mask_path}")
        with Image.open(mask_path) as original_mask:
            mask = ImageOps.exif_transpose(original_mask).convert("L")
        if mask.size != source_size:
            raise ValueError("透明度蒙版尺寸必须与源图一致")
        mask = mask.crop((left, top, right, bottom))
        result = cropped.copy()
        result.putalpha(mask)
        mask_hash = digest(mask_path)
    elif alpha_mode == "keep":
        result = cropped
    else:
        result = Image.new("RGBA", cropped.size, background)
        result.alpha_composite(cropped)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(".tmp.png")
    result.save(temporary, format="PNG")
    replace_file(temporary, output_path)

    record = {
        "sourceId": source_id,
        "path": output_path.relative_to(project).as_posix(),
        "sha256": digest(output_path),
        "sourcePath": source_path.relative_to(project).as_posix() if source_path.is_relative_to(project) else str(source_path),
        "sourceSha256": digest(source_path),
        "sourceSize": list(source_size),
        "outputSize": list(result.size),
        "alphaMode": alpha_mode,
        "crop": {
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "background": background,
            "pixelBox": {"x": left, "y": top, "w": right - left, "h": bottom - top},
        },
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "description": description,
    }
    if mask_path:
        record["alphaMaskPath"] = (
            mask_path.relative_to(project).as_posix()
            if mask_path.is_relative_to(project)
            else str(mask_path)
        )
        record["alphaMaskSha256"] = mask_hash
    if manifest_path:
        manifest_path = _project_path(project, manifest_path)
        manifest = read_json(manifest_path) if manifest_path.exists() else {"assets": []}
        if not isinstance(manifest.get("assets"), list):
            raise ValueError("素材清单必须包含 assets 数组")
        manifest["assets"] = [item for item in manifest["assets"] if item.get("sourceId") != source_id]
        manifest["assets"].append(record)
        write_json(manifest_path, manifest)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir")
    parser.add_argument("source")
    parser.add_argument("output")
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--x", type=float, required=True)
    parser.add_argument("--y", type=float, required=True)
    parser.add_argument("--width", type=float, required=True)
    parser.add_argument("--height", type=float, required=True)
    parser.add_argument("--background", default="#FFFFFF")
    parser.add_argument("--alpha-mode", choices=["flatten", "keep", "mask"], default="flatten")
    parser.add_argument("--alpha-mask")
    parser.add_argument("--focus-x", type=float)
    parser.add_argument("--focus-y", type=float)
    parser.add_argument("--manifest")
    parser.add_argument("--description", default="")
    args = parser.parse_args()
    project = Path(args.project_dir).resolve()
    source = _project_path(project, args.source)
    focus = {"x": args.focus_x, "y": args.focus_y} if args.focus_x is not None and args.focus_y is not None else None
    result = crop_asset(
        project,
        source,
        args.output,
        args.source_id,
        {"x": args.x, "y": args.y, "width": args.width, "height": args.height},
        args.background,
        focus,
        args.manifest,
        args.description,
        args.alpha_mode,
        args.alpha_mask,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        sys.exit(1)
