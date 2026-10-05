"""Shared unit conversion for the 16:9 PPTX workflow."""

from __future__ import annotations

from math import isfinite

PPI = 144
PREVIEW_WIDTH = 1920
PREVIEW_HEIGHT = 1080
SLIDE_WIDTH_INCHES = PREVIEW_WIDTH / PPI
SLIDE_HEIGHT_INCHES = PREVIEW_HEIGHT / PPI


def _finite(value, name):
    value = float(value)
    if not isfinite(value):
        raise ValueError(f"{name} 必须是有限数值")
    return value


def px_to_inch(value):
    return _finite(value, "像素") / PPI


def inch_to_px(value):
    return _finite(value, "英寸") * PPI


def pt_to_px(value):
    return _finite(value, "点") * 2


def px_to_pt(value):
    return _finite(value, "像素") / 2


def letter_spacing_px_to_pt(value):
    return px_to_pt(value)


def normalized_box_to_px(box, width=PREVIEW_WIDTH, height=PREVIEW_HEIGHT):
    x = _finite(box["x"], "x") * width
    y = _finite(box["y"], "y") * height
    w = _finite(box["w"], "w") * width
    h = _finite(box["h"], "h") * height
    return {"x": round(x), "y": round(y), "w": max(1, round(w)), "h": max(1, round(h))}


def pixel_box_to_inches(box, canvas_width=SLIDE_WIDTH_INCHES, canvas_height=SLIDE_HEIGHT_INCHES):
    return {
        "x": _finite(box["x"], "x") / PREVIEW_WIDTH * canvas_width,
        "y": _finite(box["y"], "y") / PREVIEW_HEIGHT * canvas_height,
        "w": _finite(box["w"], "w") / PREVIEW_WIDTH * canvas_width,
        "h": _finite(box["h"], "h") / PREVIEW_HEIGHT * canvas_height,
    }


def normalized_box_to_inches(box, canvas_width=SLIDE_WIDTH_INCHES, canvas_height=SLIDE_HEIGHT_INCHES):
    return {
        "x": _finite(box["x"], "x") * canvas_width,
        "y": _finite(box["y"], "y") * canvas_height,
        "w": _finite(box["w"], "w") * canvas_width,
        "h": _finite(box["h"], "h") * canvas_height,
    }
