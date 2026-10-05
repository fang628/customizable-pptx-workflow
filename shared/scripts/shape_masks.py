"""Geometric shape geometry and alpha masks shared by the bakers."""

from __future__ import annotations

import math

from PIL import Image, ImageChops, ImageDraw


def shape_points(shape, width, height):
    """Normalized-ish polygon points for the supported decorative shapes."""
    w, h = width, height
    if shape == "triangle":
        return [(w / 2, 0), (w, h), (0, h)]
    if shape == "parallelogram":
        return [(w * 0.22, 0), (w, 0), (w * 0.78, h), (0, h)]
    if shape == "trapezoid":
        return [(w * 0.18, 0), (w * 0.82, 0), (w, h), (0, h)]
    if shape == "hexagon":
        return [(w * 0.25, 0), (w * 0.75, 0), (w, h / 2),
                (w * 0.75, h), (w * 0.25, h), (0, h / 2)]
    if shape == "chevron":
        return [(0, 0), (w * 0.72, 0), (w, h / 2),
                (w * 0.72, h), (0, h), (w * 0.28, h / 2)]
    if shape == "arrow-right":
        return [(0, h * 0.25), (w * 0.62, h * 0.25), (w * 0.62, 0),
                (w, h / 2), (w * 0.62, h), (w * 0.62, h * 0.75),
                (0, h * 0.75)]
    if shape == "arrow-left":
        return [(w, h * 0.25), (w * 0.38, h * 0.25), (w * 0.38, 0),
                (0, h / 2), (w * 0.38, h), (w * 0.38, h * 0.75),
                (w, h * 0.75)]
    if shape == "arrow-up":
        return [(w * 0.25, h), (w * 0.25, h * 0.38), (0, h * 0.38),
                (w / 2, 0), (w, h * 0.38), (w * 0.75, h * 0.38),
                (w * 0.75, h)]
    if shape == "arrow-down":
        return [(w * 0.25, 0), (w * 0.25, h * 0.62), (0, h * 0.62),
                (w / 2, h), (w, h * 0.62), (w * 0.75, h * 0.62),
                (w * 0.75, 0)]
    if shape == "pentagon":
        return [(w / 2, 0), (w, h * 0.38), (w * 0.8, h),
                (w * 0.2, h), (0, h * 0.38)]
    if shape == "right-pentagon":
        # 两个直角（左边两端）+ 一对平行边（上下边）+ 上下对称，锐角朝右
        return [(0, 0), (w * 0.58, 0), (w, h / 2), (w * 0.58, h), (0, h)]
    if shape == "diamond":
        return [(w / 2, 0), (w, h / 2), (w / 2, h), (0, h / 2)]
    if shape == "v-shape":
        return [(0, 0), (w * 0.5, h * 0.62), (w, 0), (w, h * 0.38),
                (w * 0.5, h), (0, h * 0.38)]
    return [(0, 0), (w, 0), (w, h), (0, h)]


def polygon_mask(size, points):
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).polygon(points, fill=255)
    return mask


def make_mask(mask_name, size):
    """Return an L mask for the supported asset masks, or None for none."""
    width, height = size
    if mask_name in {"circle", "ellipse", "bubble"}:
        return polygon_mask(
            size,
            [
                (
                    width / 2 + math.cos(math.tau * index / 96) * width / 2,
                    height / 2 + math.sin(math.tau * index / 96) * height / 2,
                )
                for index in range(96)
            ],
        )
    if mask_name == "capsule":
        mask = Image.new("L", size, 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            (0, 0, width - 1, height - 1),
            radius=max(1, min(width, height) // 2),
            fill=255,
        )
        return mask
    if mask_name == "rounded-rectangle":
        mask = Image.new("L", size, 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            (0, 0, width - 1, height - 1),
            radius=max(1, min(width, height) // 8),
            fill=255,
        )
        return mask
    if mask_name in {"hexagon", "trapezoid", "parallelogram"}:
        return polygon_mask(size, shape_points(mask_name, width, height))
    return None


def apply_mask(image, mask):
    if mask is None:
        return image
    result = image.convert("RGBA")
    result.putalpha(ImageChops.multiply(result.getchannel("A"), mask))
    return result


def boundary_mask(spec, size, scale=4):
    """Local 0..1 polygon; curved edges use sampled arc/Bezier points."""
    points = spec.get("points", [])
    if len(points) < 3 or any(
        not isinstance(point, dict) or any(
            not isinstance(point.get(key), (int, float))
            or isinstance(point[key], bool) or not math.isfinite(point[key])
            or not 0 <= point[key] <= 1 for key in ("x", "y")
        ) for point in points
    ):
        raise ValueError("boundaryMask 需要至少三个有限的归一化轮廓点（0–1）")
    area = sum(points[i]["x"] * points[(i + 1) % len(points)]["y"]
               - points[(i + 1) % len(points)]["x"] * points[i]["y"]
               for i in range(len(points)))
    if abs(area) < 1e-10:
        raise ValueError("boundaryMask 轮廓必须围成非零面积")
    width, height = size
    mask = polygon_mask((width * scale, height * scale), [
        (point["x"] * (width * scale - 1), point["y"] * (height * scale - 1))
        for point in points
    ])
    return mask.resize(size, Image.Resampling.LANCZOS)


def shape_transform(element):
    """Provenance record for a shape element, shared by validators."""
    return {
        "shape": element["shape"],
        "fill": element.get("fill"),
        "stroke": element.get("stroke"),
        "strokeWidth": element.get("strokeWidth", 0),
        "points": element.get("points"),
        "highlight": element.get("highlight"),
        "highlightOpacity": element.get("highlightOpacity"),
        "startAngle": element.get("startAngle"),
        "endAngle": element.get("endAngle"),
        "lineCount": element.get("lineCount"),
        "lineSpacing": element.get("lineSpacing"),
        "lineThickness": element.get("lineThickness"),
        "lineAngle": element.get("lineAngle"),
        "dotRadius": element.get("dotRadius"),
        "dotSpacing": element.get("dotSpacing"),
        "rows": element.get("rows"),
        "columns": element.get("columns"),
        "bands": element.get("bands"),
        "direction": element.get("direction"),
        "ratios": element.get("ratios"),
        "skewX": element.get("skewX"),
        "skewY": element.get("skewY"),
    }
