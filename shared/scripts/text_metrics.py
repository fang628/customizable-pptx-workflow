"""Shared font resolution, CJK-aware wrapping and text-layout metrics.

Both the text fitting helpers and the measurement helpers use
this module so the estimated layout always matches what is actually drawn.
"""

from __future__ import annotations

import os
from pathlib import Path
import re

from PIL import Image, ImageDraw, ImageFont

import qa_rules

FONT_DIR = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"

# Family name -> candidate font files. The first existing file wins.
FONT_FAMILIES = {
    "Microsoft YaHei": ["msyh.ttc", "msyhbd.ttc", "msyhl.ttc"],
    "SimHei": ["simhei.ttf"],
    "SimSun": ["simsun.ttc", "simsunb.ttf"],
    "DengXian": ["Deng.ttf", "Dengb.ttf"],
    "KaiTi": ["simkai.ttf"],
    "FangSong": ["simfang.ttf"],
    "Source Han Sans": ["SourceHanSansSC-Regular.otf", "SourceHanSansSC-Bold.otf"],
    "Noto Sans CJK": ["NotoSansCJK-Regular.ttc", "NotoSansCJKsc-Regular.otf"],
    "Arial": ["arial.ttf", "arialbd.ttf"],
    "Times New Roman": ["times.ttf", "timesbd.ttf"],
    "Cambria": ["cambria.ttc", "cambriab.ttf"],
}

FONT_ALIASES = {
    "微软雅黑": "Microsoft YaHei",
    "msyh": "Microsoft YaHei",
    "雅黑": "Microsoft YaHei",
    "黑体": "SimHei",
    "simhei": "SimHei",
    "宋体": "SimSun",
    "思源黑体": "Source Han Sans",
    "source han sans": "Source Han Sans",
    "noto sans cjk": "Noto Sans CJK",
    "等线": "DengXian",
    "楷体": "KaiTi",
    "仿宋": "FangSong",
}

BOLD_TOKENS = ("bold", "black", "heavy", "hei", "黑体", "粗")
BOLD_FALLBACK = ["msyhbd.ttc", "simhei.ttf", "arialbd.ttf", "arial.ttf"]
REGULAR_FALLBACK = ["msyh.ttc", "simhei.ttf", "arial.ttf"]

_CJK = re.compile(r"[\u3000-\u9fff\uff00-\uffef]")
_TOKEN = re.compile(r"[A-Za-z0-9]+(?:[.\-/:%;%‰°][A-Za-z0-9]+)*|.")
_NO_LINE_START = set("、。，．；：？！）】》」』”’…·%,.;:?!)]}")
_NO_LINE_END = set("（【《「『“‘([{<")

_MEASURE = ImageDraw.Draw(Image.new("L", (4, 4)))


def canonical_family(font_face):
    name = (font_face or "").strip()
    lowered = name.lower()
    if lowered in FONT_ALIASES:
        return FONT_ALIASES[lowered]
    for alias, family in FONT_ALIASES.items():
        if alias in lowered:
            return family
    for family in FONT_FAMILIES:
        if family.lower() in lowered:
            return family
    if any(token in lowered for token in BOLD_TOKENS):
        for family in ("Microsoft YaHei", "SimHei", "Arial"):
            if family.lower().split()[0] in lowered:
                return family
    return name


def wants_bold(font_face):
    lowered = (font_face or "").lower()
    return any(token in lowered for token in BOLD_TOKENS)


def family_files(font_face, weight="default"):
    family = canonical_family(font_face)
    names = FONT_FAMILIES.get(family)
    if not names:
        return []
    if weight == "bold" or wants_bold(font_face):
        ordered = [name for name in names if any(token in name.lower() for token in ("bd", "bold", "hei"))]
        ordered += [name for name in names if name not in ordered]
    else:
        ordered = [name for name in names if not any(token in name.lower() for token in ("bd", "bold"))]
        ordered += [name for name in names if name not in ordered]
    return [FONT_DIR / name for name in ordered]


def font_fallback(font_face):
    """True when the requested family is not installed and another face is used."""
    candidates = family_files(font_face)
    if not candidates:
        return True
    return not any(path.is_file() for path in candidates)


def font_path(font_face, weight="default"):
    for candidate in family_files(font_face, weight):
        if candidate.is_file():
            return candidate
    fallback = BOLD_FALLBACK if weight == "bold" else REGULAR_FALLBACK
    for name in fallback:
        candidate = FONT_DIR / name
        if candidate.is_file():
            return candidate
    return None


def resolve_font(font_face, size, bold=False):
    """Return (font, resolved_path). resolved_path is None for the bitmap default."""
    path = font_path(font_face, "bold" if bold else "default")
    if path:
        return ImageFont.truetype(str(path), size=size), path
    return ImageFont.load_default(size=size), None


def has_cjk(text):
    return bool(_CJK.search(str(text)))


def font_status():
    """Inventory of the known families, for environment checks."""
    report = {}
    for family, names in FONT_FAMILIES.items():
        found = [name for name in names if (FONT_DIR / name).is_file()]
        report[family] = {
            "found": found,
            "missing": [name for name in names if name not in found],
            "ready": bool(found),
            "bold_ready": any(
                any(token in name.lower() for token in ("bd", "bold")) for name in found
            ),
        }
    return report


def font_provenance(font_face, size):
    """Provenance-friendly font record shared by the text helpers."""
    path = font_path(font_face or "")
    return {
        "fontResolved": str(path) if path else None,
        "fontFallback": font_fallback(font_face or ""),
    }


def wrap_text(draw, text, font, max_width):
    """Wrap CJK text per character, keep Latin words whole and avoid line-start punctuation."""
    lines = []
    for paragraph in str(text).splitlines() or [""]:
        if not paragraph:
            lines.append("")
            continue
        current = ""
        for token in _TOKEN.findall(paragraph):
            candidate = current + token
            if current and draw.textlength(candidate, font=font) > max_width:
                if token in _NO_LINE_START:
                    lines.append(candidate)
                    current = ""
                    continue
                if current[-1:] in _NO_LINE_END:
                    lines.append(current + token)
                    current = ""
                    continue
                lines.append(current)
                current = token
            else:
                current = candidate
            while draw.textlength(current, font=font) > max_width and len(current) > 1:
                cut = len(current) - 1
                while cut > 1 and draw.textlength(current[:cut], font=font) > max_width:
                    cut -= 1
                lines.append(current[:cut])
                current = current[cut:]
        lines.append(current)
    return lines or [""]


def text_metrics(element, box_px, size=None):
    """Estimate the drawn text layout inside a pixel box."""
    box_px = _box_tuple(box_px)
    x, y, width, height = box_px
    font_face = element.get("fontFace") or ""
    size = int(size if size is not None else element["fontSize"])
    font, resolved = resolve_font(font_face, size, bold=wants_bold(font_face))
    lines = wrap_text(_MEASURE, element["text"], font, width)
    line_spacing = float(element.get("lineSpacing", 1.15))
    heights = []
    widths = []
    for line in lines:
        box = _MEASURE.textbbox((0, 0), line or " ", font=font)
        heights.append(box[3] - box[1])
        widths.append(box[2] - box[0])
    line_step = round(max(heights or [size]) * line_spacing)
    total_height = line_step * len(lines)
    valign = element.get("valign", "top")
    align = element.get("align", "left")
    if valign == "middle":
        start_y = y + (height - total_height) / 2
    elif valign == "bottom":
        start_y = y + height - total_height
    else:
        start_y = y
    ink_boxes = []
    draw_positions = []
    for index, line in enumerate(lines):
        box = _MEASURE.textbbox((0, 0), line or " ", font=font)
        line_width = box[2] - box[0]
        if align == "center":
            text_x = x + (width - line_width) / 2
        elif align == "right":
            text_x = x + width - line_width
        else:
            text_x = x
        top = start_y + index * line_step
        draw_positions.append((text_x, top - box[1]))
        ink_boxes.append(
            (text_x + box[0], top + box[1], text_x + box[2], top + box[3])
        )
    tolerance = qa_rules.OVERFLOW_TOLERANCE
    return {
        "lines": lines,
        "line_count": len(lines),
        "font": font,
        "font_size": size,
        "font_face": font_face,
        "line_step": line_step,
        "total_height": total_height,
        "max_line_width": max(widths or [0]),
        "ink_boxes": ink_boxes,
        "draw_positions": draw_positions,
        "font_resolved": str(resolved) if resolved else None,
        "font_fallback": font_fallback(font_face) if font_face else True,
        "bitmap_default": resolved is None,
        "overflow_height": total_height > height * tolerance,
        "overflow_width": (max(widths or [0]) > width * tolerance),
    }


def fits(metrics):
    return not metrics["overflow_height"] and not metrics["overflow_width"]


def _box_tuple(box):
    if isinstance(box, dict):
        return (box["x"], box["y"], box["w"], box["h"])
    return tuple(box)


def fit_text_size(element, box_px):
    """Resolve the drawn size: declared, or shrunk by `autofit` down to the floor."""
    declared = int(element["fontSize"])
    metrics = text_metrics(element, box_px, size=declared)
    if not element.get("autofit") or fits(metrics):
        return declared, metrics
    floor = max(
        int(qa_rules.text_floor(element)),
        int(round(declared * qa_rules.AUTOFIT_MIN_SCALE)),
    )
    size = declared
    while size > floor:
        size -= 1
        metrics = text_metrics(element, box_px, size=size)
        if fits(metrics):
            break
    return size, metrics


def element_font_size(element, box_px):
    """The font size actually used for a text box at the given size."""
    if element.get("type") != "text":
        return int(element.get("fontSize") or 0)
    return fit_text_size(element, box_px)[0]
