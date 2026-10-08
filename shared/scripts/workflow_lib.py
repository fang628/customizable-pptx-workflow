"""Shared project contracts, fingerprints and validation helpers."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

from jsonschema import Draft202012Validator
from PIL import Image
from preview_originals import insertion_errors, local_frame_errors
from asset_cutout import cutout_transform, edge_transform
from imagegen_adapter import resolve_script
from preview_images import asset_image_errors, image_errors, stage_preview_errors
from qa_rules import (
    RULES_VERSION,
    SAME_STYLE_PALETTE_TOLERANCE,
    PHOTO_FRAME_ASPECT_TOLERANCE,
    PHOTO_FRAME_ASPECT_RELAXED_TOLERANCE,
    PLACEHOLDER_BOX_TOLERANCE,
    TEXT_BOX_COVER,
    text_role,
)
from shape_masks import shape_transform, boundary_mask
from text_metrics import element_font_size, fit_text_size, fits, font_provenance
from units import inch_to_px, normalized_box_to_inches, normalized_box_to_px, pt_to_px

ROOT = Path(__file__).resolve().parents[2]
STAGES = ["0", "1.1", "1.2", "1.3", "2.1", "2.2", "3.1", "3.2", "3.3", "4"]
# 三个候选设计方向：与阶段 2.1 的 option-a/b/c 以及候选图的 styleId 一一对应。
STYLE_IDS = ("a", "b", "c")
# 停机点：只有这些阶段允许暂停等用户；其余阶段必须一次跑完，不得中途结束任务进程。
STOP_POINTS = {
    "1.1": "需求与材料确认",
    "1.3": "设计稿复核",
    "2.1": "A/B/C 方案确认",
    "2.2": "完整预览批准",
}
STOP_POINT_ORDER = ("1.1", "1.3", "2.1", "2.2")
ARTIFACTS = {
    "1.1": ["00_intake/project-brief.md", "00_intake/ai-image-config.json", "01_inventory/material-inventory.md", "01_inventory/materials.json", "00_intake/requirements-approval.json"],
    "1.2": ["02_design/content-plan.md", "02_design/generated-assets.json", "02_design/generated-assets/*.png", "02_design/generation-jobs.json", "02_design/generation-ledger.json"],
    "1.3": ["02_design/design-spec.md", "02_design/content.json", "02_design/claim-map.json", "02_design/generated-assets.json", "02_design/image-intent-plan.json"],
    "2.1": ["02_design/split-references*", "02_design/split-references/**/*.png", "03_concepts/concept-review.md", "03_concepts/approved-direction.md", "03_concepts/approval.json", "03_concepts/generation-jobs.json", "03_concepts/generation-ledger.json", "03_concepts/option-*/preview.json", "03_concepts/option-*/*.png", "03_concepts/raw/**/*.png"],
    "2.2": ["02_design/image-plan.json", "04_full-preview/previews.json", "04_full-preview/raw/**/*.png", "04_full-preview/slides/*.png", "04_full-preview/generation-jobs.json", "04_full-preview/generation-ledger.json", "04_full-preview/generation-log.md", "04_full-preview/approval.json"],
    "3.1": ["05_reconstruction/element-inventory.md", "05_reconstruction/slide-elements.md"],
    "3.2": ["05_reconstruction/assets.json", "05_reconstruction/photos/*", "05_reconstruction/vectors/*", "05_reconstruction/rasters/*", "05_reconstruction/cutouts/*"],
    "4": ["08_speaker-notes/notes.json", "08_speaker-notes/speaker-script.md"],
    "3.3": ["06_build/deck-spec.json", "07_delivery/deck.pptx", "07_delivery/build-manifest.json", "07_delivery/render-manifest.json", "07_delivery/review-manifest.json", "07_delivery/qa-review.json", "07_delivery/qa-report.md", "07_delivery/preview/**/*.png", "07_delivery/review/**/*.png"],
}


def now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    replace_file(temporary, path)


@contextmanager
def project_lock(project, stale_after=600):
    """Serialize writers on one project: state, ledger, previews and builds."""
    path = Path(project) / "workflow.lock"
    payload = json.dumps({"pid": os.getpid(), "at": now()})
    acquired = False
    for attempt in range(2):
        try:
            handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(handle, payload.encode("utf-8"))
            os.close(handle)
            acquired = True
            break
        except FileExistsError:
            age = stale_after + 1
            try:
                age = time.time() - datetime.fromisoformat(read_json(path)["at"]).timestamp()
            except (OSError, ValueError, TypeError, KeyError):
                pass
            if age > stale_after:
                try:
                    path.unlink()
                except OSError:
                    pass
                continue
            raise ValueError(
                "该项目正在被另一个进程写入（workflow.lock 存在）；"
                "不要并行运行生成器、组装或构建"
            ) from None
    if not acquired:
        raise ValueError("无法获取项目写入锁：workflow.lock")
    try:
        yield path
    finally:
        try:
            path.unlink()
        except OSError:
            pass


def replace_file(temporary, path, attempts=6, delay=0.05):
    """Atomically move a temporary file into place, tolerating Windows file locks."""
    temporary, path = Path(temporary), Path(path)
    for attempt in range(attempts):
        try:
            temporary.replace(path)
            return path
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay * (attempt + 1))
    return path


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def asset_path(project, value):
    path = Path(value)
    return path if path.is_absolute() else project / path


def schema_errors(value, name):
    schema = read_json(ROOT / "shared/schemas" / f"{name}.schema.json")
    return [f"{name}:{'/'.join(map(str, error.absolute_path)) or '/'}: {error.message}"
            for error in Draft202012Validator(schema).iter_errors(value)]


def reference_category_errors(content):
    """Validate optional reference selections against the skill taxonomy."""
    errors = []
    categories = read_json(ROOT / "stages/13-design/references/reference-categories.json")["categories"]
    by_id = {category["id"]: category for category in categories}
    for slide in content["slides"]:
        selected_ids = slide.get("reference_categories", [])
        reference_ids = slide.get("reference_ids", [])
        if not selected_ids and not reference_ids:
            continue
        if not selected_ids:
            errors.append(f"{slide['id']} 引用了参考图但未指定 reference_categories")
            continue
        selected = []
        for category_id in selected_ids:
            category = by_id.get(category_id)
            if not category:
                errors.append(f"{slide['id']} 引用了不存在的参考类别：{category_id}")
                continue
            expected_type = (
                "title" if slide["page_type"] == "thanks" else slide["page_type"]
            )
            if category["page_type"] != expected_type or category["layout_id"] != slide["layout_id"]:
                errors.append(
                    f"{slide['id']} 的参考类别 {category_id} 与 "
                    f"{slide['page_type']}/{slide['layout_id']} 不一致"
                )
            selected.append(category)
        allowed_references = {
            reference_id
            for category in selected
            for reference_id in category["reference_ids"]
        }
        for reference_id in reference_ids:
            if reference_id not in allowed_references:
                errors.append(f"{slide['id']} 的参考图 {reference_id} 不属于所选类别")
    return errors


def collect(project, stage):
    paths = []
    for pattern in ARTIFACTS.get(stage, []):
        if "*" in pattern:
            paths.extend(p for p in project.glob(pattern) if p.is_file())
        else:
            path = project / pattern
            if not path.is_file() or not path.stat().st_size:
                raise ValueError(f"缺少阶段 {stage} 产物：{pattern}")
            paths.append(path)
    return {str(path.relative_to(project)).replace("\\", "/"): digest(path) for path in sorted(set(paths))}


def check_hashes(project, files):
    errors = []
    if not isinstance(files, dict) or not files:
        return ["缺少有效文件指纹记录"]
    for relative, expected in files.items():
        path = asset_path(project, relative)
        if not path.is_file():
            errors.append(f"文件已缺失：{relative}")
        elif digest(path) != expected:
            errors.append(f"文件版本已变化：{relative}")
    return errors


# 分块参考图索引：形态样例与「提示词怎么写」都放在 shared/references/splits 里。
SPLIT_REFERENCE_INDEX = ROOT / "shared/references/splits/index.json"
SPLIT_REFERENCE_ROOT = "02_design/split-references"
DEFAULT_SPECIAL_SPLITS = (
    "斜切", "弧线", "扇形", "同心圆", "波浪", "金字塔", "圆形放射", "左圆右栏",
)


def split_reference_index():
    """分块参考图索引：每条含名称、形态、提示词写法与参考图文件。"""
    entries = []
    data = read_json(SPLIT_REFERENCE_INDEX)
    for key, kind in (("splits", "special"), ("macro", "macro")):
        for entry in data.get(key, []) or []:
            entries.append({**entry, "kind": entry.get("kind", kind)})
    return entries


def split_entries(cell):
    """设计稿《页面分块要求》单元格里点到的分块条目（按索引顺序）。"""
    text_value = str(cell or "")
    matched = []
    for entry in split_reference_index():
        tokens = [entry.get("name", ""), entry.get("label", "")]
        tokens += list(entry.get("aliases") or [])
        if any(token and token in text_value for token in tokens):
            matched.append(entry)
    return matched


def split_reference_path(entry):
    """该分块条目随任务交给 AI 的参考图（项目内相对路径）。"""
    return f"{SPLIT_REFERENCE_ROOT}/{entry['id']}/{entry['default']}"


def _special_split_names():
    try:
        return tuple(
            entry["name"] for entry in split_reference_index() if entry["kind"] == "special"
        )
    except (OSError, ValueError, TypeError, KeyError):
        return DEFAULT_SPECIAL_SPLITS


SPECIAL_SPLITS = _special_split_names()


def page_split_rows(design_spec):
    """《页面分块要求》表的 (页面编号, 分块方式) 行。"""
    block = design_spec.split("## 页面分块要求", 1)[-1]
    block = block.split("\n## ", 1)[0]
    rows = []
    for line in block.splitlines():
        line = line.strip()
        if not line.startswith("| S"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) >= 2:
            rows.append((cells[0], cells[1]))
    return rows


TEXTBOX_SHAPE_TOKENS = (
    "无文本框",
    "直角五边形",
    "圆角矩形",
    "弧线条带",
    "分色色块",
    "平行四边形",
    "六边形",
    "五边形",
    "胶囊形",
    "胶囊",
    "气泡",
    "椭圆",
    "圆形",
    "梯形",
    "菱形",
    "三角形",
    "矩形",
    "色块",
    "色带",
    "箭形",
)
CANVAS_RATIO_TOKENS = ("16:9", "16：9", "1920×1080", "1920x1080", "1920*1080")
# 页内文字间逻辑关系的表达方式：箭头或箭形色块
LOGIC_ARROW_TOKENS = ("箭头", "箭形")
# 提示词要强调图片占位框的宽高比固定不变
RATIO_LOCK_TOKENS = (
    "不能改变", "不要改变", "不得改变", "不可改变", "不能变", "比例不变",
    "不变形", "不能变形", "不拉伸", "不要拉伸", "不得拉伸", "保持比例", "保持宽高比",
)
# 阶段 1.2 的大图候选（封面／目录／背景底图）：提示词要写明 16:9 比例
BIG_IMAGE_JOB_TOKENS = (
    "hero-image", "toc-image", "content-background", "thanks-image",
    "封面大图", "标题图", "目录页大图", "目录页主图", "目录图", "背景底图", "背景图",
)
PALETTE_MATCH_TOKENS = (
    "同一套配色", "同色系", "配色相近", "配色一致", "颜色相近", "相近的颜色",
    "相近的配色", "与大图配色一致",
)
NO_PROGRESS_TOKENS = ("无进度条", "不加进度条", "不要进度条", "不画进度条", "不需要进度条")
# 提示词使用Markdown列表，排版要求内部按实际分块嵌套
POINT_LABELS = ("比例要求", "内容要求", "排版要求", "图片占位框比例", "风格要求", "进度条要求")


def prompt_points(prompt):
    """提示词的分点条目（去掉行首的编号与项目符号），用来核对是否按点分条写。"""
    points = []
    for line in prompt.splitlines():
        line = re.sub(r"^\s*(?:[-+•·*]|\d+[.、)]|[①-⑩])\s*", "", line)
        if line.strip():
            points.append(re.sub(r"\*\*|__", "", line).strip())
    return points


def prompt_emphasis_errors(prompt):
    """Check three top-level goals and two required children of style."""
    entries = []
    for line in prompt.splitlines():
        match = re.match(r"^( *)(?:[-+*]|\d+[.)])\s+(.+)$", line)
        if match:
            entries.append((len(match.group(1)), re.sub(r"\*\*|__", "", match.group(2)).strip()))
    base = min((indent for indent, _ in entries), default=0)
    top = [body for indent, body in entries if indent == base]
    errors = []
    for label in ("可读性要求", "视觉关系要求", "原图保真要求"):
        if not any(re.match(re.escape(label) + r"[：:]\s*\S", body) for body in top):
            errors.append(f"提示词须单独填写顶层列表项「{label}」，不能仅在内容或其他条目中提及")
    style_children = []
    in_style = False
    for indent, body in entries:
        if indent == base:
            in_style = bool(re.match(r"风格要求[：:]", body))
        elif in_style:
            style_children.append(body)
    for label in ("简约要求", "紧密排版要求"):
        if not any(re.match(re.escape(label) + r"[：:]\s*\S", body) for body in style_children):
            errors.append(f"提示词的「风格要求」必须含非空子项「{label}」，不能省略或仅在其他条目中提及")
    return errors


def prompt_markdown_layout_errors(prompt):
    """Check list nesting, not the truth or completeness of spatial descriptions."""
    entries = []
    for line in prompt.splitlines():
        match = re.match(r"^( *)(?:[-+*]|\d+[.)])\s+(.+)$", line)
        if match:
            body = re.sub(r"\*\*|__", "", match.group(2)).strip()
            entries.append((len(match.group(1)), body))
    layout = next((i for i, (_, body) in enumerate(entries)
                   if body.startswith("排版要求")), None)
    if layout is None:
        return ["提示词必须用Markdown列表撰写，并在排版要求下嵌套实际分块与元素"]
    base = entries[layout][0]
    subtree = []
    for indent, body in entries[layout + 1:]:
        if indent <= base:
            break
        subtree.append((indent, body))
    if len({indent for indent, _ in subtree}) < 2:
        return ["排版要求须使用嵌套列表展开宏观分块及其子分块／所属元素，不能平铺所有对象"]
    return []


PAGE_TYPE_KIND = {
    "title": "hero-image",
    "toc": "toc-image",
    "thanks": "content-background",
    "content": "content-background",
}


def palette_signature(path, size=(64, 36), exclude_boxes=None):
    """图片主色签名：量化成几色的 (颜色, 权重) 列表，用来比对同风格配色。"""
    with Image.open(path) as opened:
        frame = opened.convert("RGB")
    frame.thumbnail(size)
    if exclude_boxes:
        # Compare the background/decorations, not intentional scientific
        # placeholders or high-contrast text carriers from the design spec.
        width, height = frame.size
        pixels = [frame.getpixel((x, y)) for y in range(height) for x in range(width)
                  if not any(b['x'] <= (x + .5) / width <= b['x'] + b['w']
                             and b['y'] <= (y + .5) / height <= b['y'] + b['h']
                             for b in exclude_boxes)]
        if pixels:
            frame = Image.new('RGB', (len(pixels), 1))
            frame.putdata(pixels)
    quantized = frame.quantize(colors=4, method=Image.Quantize.MEDIANCUT)
    palette = quantized.getpalette() or []
    counts = sorted(quantized.getcolors() or [], reverse=True)
    total = sum(count for count, _ in counts) or 1
    return [
        (tuple(palette[index * 3:index * 3 + 3]), count / total)
        for count, index in counts
    ]


def palette_distance(left, right):
    """两组主色的加权最小距离（0 表示完全一致）。"""
    total = 0.0
    weight = 0.0
    for color, share in left:
        if not right:
            return 0.0
        total += share * min(math.dist(color, other) for other, _ in right)
        weight += share
    return total / weight if weight else 0.0


def preview_direction(project, stage, option):
    """当前阶段使用的风格方向：2.1 用方案号，2.2 用已确认方向。"""
    if stage == "2.1":
        return option
    record = project / "03_concepts/approved-direction.md"
    if record.is_file():
        match = re.search(r"选定方案：\s*([ABCabc])", record.read_text(encoding="utf-8-sig"))
        if match:
            return match.group(1).lower()
    return None


def preview_palette_warnings(project, stage, option, pages):
    """Diagnostic palette distance; visual review decides reasonable style variation."""
    direction = preview_direction(project, stage, option)
    if not direction:
        return []
    assets_path = project / "02_design/generated-assets.json"
    if not assets_path.is_file():
        return []
    by_kind = {}
    for asset in read_json(assets_path).get("assets", []):
        if str(asset.get("styleId") or "").lower() != str(direction).lower():
            continue
        kind = asset.get("kind")
        path = asset_path(project, asset.get("path") or "")
        if kind in PAGE_TYPE_KIND.values() and path.is_file():
            by_kind.setdefault(kind, path)
    content = read_json(project / "02_design/content.json")
    page_type = {slide["id"]: slide.get("page_type") for slide in content["slides"]}
    errors = []
    excluded_by_page = {}
    spec_path = project / '02_design/design-spec.md'
    if spec_path.is_file():
        for match in re.finditer(r'`(S\d+)-[^`]+`：x=([0-9.]+)，y=([0-9.]+)，w=([0-9.]+)，h=([0-9.]+)', spec_path.read_text(encoding='utf-8-sig')):
            excluded_by_page.setdefault(match[1], []).append(dict(zip(('x', 'y', 'w', 'h'), map(float, match.groups()[1:]))))
    for page in pages:
        source = by_kind.get(PAGE_TYPE_KIND.get(page_type.get(page["id"])))
        file = project / page["file"]
        if not source or not file.is_file():
            continue
        try:
            share = palette_distance(palette_signature(file, exclude_boxes=excluded_by_page.get(page['id'])), palette_signature(source))
        except (OSError, ValueError, TypeError):
            continue
        if share > SAME_STYLE_PALETTE_TOLERANCE:
            errors.append(
                f"{page['id']} 的整页预览与同风格的 AI 大图配色相差过大（主色距离 {share:.0f}）："
                "请复看配色语义与可读性；合理浅深变化可在 review 中说明，不单凭距离拒绝"
            )
    return errors


def preview_palette_errors(project, stage, option, pages):
    """Compatibility API: numeric palette differences no longer block approval."""
    return []


ARROW_LINK_TOKENS = ("→", "->", "指向")


def design_page_plan_errors(content, design_spec):
    """Accept compact spatial trees and existing legacy plans without duplicate fields."""
    errors = []
    plan = design_spec.split("## 逐页规划", 1)[-1]
    pages = [re.split(r"^## ", page, flags=re.M)[0]
             for page in re.split(r"^### ", plan, flags=re.M)[1:]]
    compact = any("**嵌套排版树：**" in page for page in pages)
    if not compact:
        for label in ("文字层级与并列", "元素位置与大小", "上屏文案（最终文字）"):
            if f"- **{label}：**" not in design_spec:
                errors.append(f"旧版设计稿缺少「{label}」；可改为四项逐页结构，将信息统一写入嵌套排版树")
        return errors
    centralized_style = "**风格要求：**" in design_spec.split("## 逐页规划", 1)[0]
    if centralized_style:
        style = design_spec.split("## 逐页规划", 1)[0]
        if not re.search(r"\d+(?:\.\d+)?\s*pt", style, re.I):
            errors.append("集中风格要求未注明角色默认字号pt")
    by_id = {slide["id"]: slide for slide in content["slides"]}
    seen = set()
    for page in pages:
        page_id = page.split("：", 1)[0].strip()
        if page_id in seen:
            errors.append(f"逐页规划重复页面：{page_id}")
        seen.add(page_id)
        if "**嵌套排版树：**" not in page:
            continue  # Mixed documents can retain unchanged legacy page sections.
        for label in ("页面信息", "页面目的与阅读逻辑", "嵌套排版树", "本页视觉差异与特殊说明"):
            match = re.search(r"^- \*\*" + re.escape(label) + r"：\*\*([^\n]*(?:\n(?!- \*\*|###|##)[^\n]*)*)", page, re.M)
            if not match or not match.group(1).strip():
                errors.append(f"{page_id} 缺少或未填写「{label}」")
        errors += [f"{page_id} 的嵌套排版树：{error}"
                   for error in prompt_markdown_layout_errors(page.replace("嵌套排版树", "排版要求", 1))]
        tree = page.split("**嵌套排版树：**", 1)[1].split("- **本页视觉差异与特殊说明：**", 1)[0]
        slide = by_id.get(page_id)
        if slide is None:
            errors.append(f"逐页规划引用未知页面：{page_id}")
            continue
        for text in slide.get("texts") or []:
            identifier = text["id"]
            occurrences = []
            for match in re.finditer(r"(?<![A-Za-z0-9_-])" + re.escape(identifier) + r"(?![A-Za-z0-9_-])", tree):
                line_start = tree.rfind("\n", 0, match.start()) + 1
                declaration = tree[line_start:].split("\n", 1)[0]
                # References in arrows can repeat an ID; only the object's
                # declaration is required to appear once.
                if (re.search(r"文字|文本", declaration)
                        and not re.search(r"箭头|连接", declaration)):
                    occurrences.append(match)
            if len(occurrences) != 1:
                errors.append(f"{page_id} 的文字 {identifier} 应在排版树中记录一次文案与文本框")
                continue
            start = tree.rfind("\n", 0, occurrences[0].start()) + 1
            line = tree[start:].split("\n", 1)[0]
            indent = len(line) - len(line.lstrip())
            following = tree[start + len(line):]
            stop = re.search(r"\n {0," + str(indent) + r"}(?:[-+*]|\d+[.)])\s", following)
            node = line + (following[:stop.start()] if stop else following)
            if str(text.get("text") or "").strip() not in node:
                errors.append(f"{page_id} 的文字 {identifier} 最终文案未写入对应对象或与content.json不一致")
            if not centralized_style and "文本框：" not in node:
                errors.append(f"{page_id} 的文字 {identifier} 未写明文本框形状／无文本框")
            if not centralized_style and not re.search(r"\d+(?:\.\d+)?\s*pt|字号[^\n]*继承全篇", node, re.I):
                errors.append(f"{page_id} 的文字 {identifier} 未注明字号pt或继承全篇角色字号")
    for identifier in set(by_id) - seen:
        errors.append(f"逐页规划缺少页面：{identifier}")
    return errors


def page_logic_arrows(design_spec):
    """设计稿逐页规划里，哪些页真的用箭头／箭形色块表达文字间的逻辑关系。

    只有同时点明指向（文字编号、"→" 或「指向」）才算声明；模板里的写法说明不算。
    """
    arrows = {}
    plan = design_spec.split("## 逐页规划", 1)[-1]
    for page in re.split(r"^### ", plan, flags=re.M)[1:]:
        page_id = page.split("：", 1)[0].strip() or "未命名页面"
        section = re.split(r"^## ", page, flags=re.M)[0]
        used = False
        for line in section.splitlines():
            if not any(token in line for token in LOGIC_ARROW_TOKENS):
                continue
            if re.search(r"S\d{2}-[A-Z]+-\d+", line) or any(
                token in line for token in ARROW_LINK_TOKENS
            ):
                used = True
                break
        arrows[page_id] = used
    return arrows


def page_textbox_shapes(design_spec):
    """设计稿逐页规划里每页声明的文本框形状（含「无文本框」）。"""
    shapes = {}
    # Centralized styles are checked as a whole; do not turn suggested
    # silhouettes into per-object gates or require unused role styles.
    centralized = "**风格要求：**" in design_spec.split("## 逐页规划", 1)[0]
    plan = design_spec.split("## 逐页规划", 1)[-1]
    for page in re.split(r"^### ", plan, flags=re.M)[1:]:
        page_id = page.split("：", 1)[0].strip() or "未命名页面"
        section = re.split(r"^## ", page, flags=re.M)[0]
        found = []
        for line in section.splitlines():
            if centralized or "文本框：" not in line or "形状＋" in line:
                continue
            for token in TEXTBOX_SHAPE_TOKENS:
                if token in line and token not in found:
                    found.append(token)
        shapes[page_id] = found
    return shapes


def preview_prompt_forbidden_details(prompt, final_texts=()):
    """Reject geometry/typography directives, without mistaking slide content for instructions."""
    instructions = prompt
    for value in sorted((str(v) for v in final_texts if v), key=len, reverse=True):
        instructions = instructions.replace(value, "[文案]")
    forbidden = []
    if re.search(r"字号|字体(?:大小|尺寸)|font[\s_]*size|fontSize", instructions, re.I):
        forbidden.append("字号")
    elif re.search(r"(?:标题|正文|注释|文字|字体)\s*\d+(?:\.\d+)?\s*(?:px|pt|磅|像素|号)", instructions, re.I):
        forbidden.append("字号")
    if re.search(r"(?:文本框|文字框)[^。；\n]{0,12}(?:大小|尺寸|宽高)|(?:文本框|文字框|框)(?:宽度?|高度?)\s*[=:：＝]?\s*\d|(?:文本框|文字框)[^。；\n]{0,20}(?:宽度?|高度?|尺寸|大小|[wh])\s*[=:：＝]\s*[\d.]|(?:文本框|文字框)[^。；\n]{0,20}\d+(?:\.\d+)?\s*[×x]\s*\d+", instructions, re.I):
        forbidden.append("文本框大小")
    if re.search(r"[\"']?\b[xy][\"']?\s*[=:：＝]\s*-?[\d.]|(?:左上|坐标|横坐标|纵坐标)\s*[=:：＝（(]?\s*-?[\d.]|(?:左边距|右边距|上边距|下边距|距左|距右|距上|距下)\s*[=:：＝]?\s*\d", instructions, re.I):
        forbidden.append("元素具体位置")
    return forbidden


def preview_prompt_height_matches_content(prompt, final_texts=()):
    """Require content-sized boxes while excluding quoted slide text from instructions."""
    instructions = prompt
    for value in sorted((str(v) for v in final_texts if v), key=len, reverse=True):
        instructions = instructions.replace(value, "[文案]")
    fitted = re.search(r"(?:文本框|文字框|框高)[^。；\n]{0,65}(?:匹配|贴合|适配|适应|随|根据)[^。；\n]{0,30}(?:文本|文字|内容)", instructions)
    if not fitted:
        fitted = re.search(r"(?:文本框|文字框)[^。；\n]{0,65}(?:文本|文字|内容)[^。；\n]{0,25}(?:匹配|贴合|适配|适应)", instructions)
    restrained = re.search(r"(?:避免|不要|不得|减少)[^。；\n]{0,25}(?:大片|大量|过多|过大)[^。；\n]{0,12}(?:留白|空白)", instructions)
    return bool(fitted and restrained and re.search(r"框高|(?:文本框|文字框)[^。；\n]{0,30}高度?", instructions))


def prompt_internal_identifiers(prompt, identifiers=()):
    """Detect workflow labels, without treating public list/scientific numbers as IDs."""
    pattern = r"(?<![A-Za-z0-9_])(?:S\d{2,}(?:[-_][A-Za-z][A-Za-z0-9_-]*)?|(?:GEN|RECON|PHOTO|MAT|IMG|PIC|TEXT|SEC|CLAIM)[-_]\d[A-Za-z0-9_-]*|(?:CONCEPT|FULL)[-_][A-Za-z0-9_-]+|R\d{3,})(?![A-Za-z0-9_])"
    found = set(re.findall(pattern, prompt, flags=re.I))
    for identifier in identifiers:
        if not isinstance(identifier, str) or not identifier:
            continue
        # Pure names can also be ordinary on-screen words; only structured local
        # labels are detectable by exact matching without suppressing content.
        if not re.search(r"[0-9_-]", identifier):
            continue
        if re.search(r"(?<![A-Za-z0-9_])" + re.escape(identifier) + r"(?![A-Za-z0-9_])", prompt, flags=re.I):
            found.add(identifier)
    return sorted(found)


def project_prompt_identifiers(project, job):
    """Gather local identity fields; prompts and prose are not identity sources."""
    identifiers = {job.get("id"), job.get("asset_id"), job.get("page_id")}
    def collect(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"id", "sourceId", "textId", "imageId", "assetId", "sourceAssetId"} and isinstance(item, str):
                    identifiers.add(item)
                elif key == "reference_ids" and isinstance(item, list):
                    identifiers.update(v for v in item if isinstance(v, str))
                elif isinstance(item, (dict, list)):
                    collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)
    collect(job)
    for rel in ("02_design/content.json", "02_design/image-plan.json",
                "02_design/image-intent-plan.json", "02_design/generated-assets.json",
                "01_inventory/materials.json"):
        try:
            collect(read_json(project / rel))
        except (OSError, ValueError, TypeError):
            pass
    return identifiers


def preview_job_page_id(job, page_ids):
    """Bind pages from local metadata, never from model-facing prompt text."""
    if job.get("page_id") is not None:
        return job["page_id"] if job["page_id"] in page_ids else None
    label = str(job.get("id") or "")
    matches = [sid for sid in page_ids
               if re.search(r"(?<![A-Za-z0-9])" + re.escape(sid) + r"(?![A-Za-z0-9])", label)]
    return matches[0] if len(matches) == 1 else None


def preview_prompt_errors(project, stage, job_ids=None):
    """阶段 2.1／2.2：生成前自检每页提示词——画布比例、占位块与比例、文字与文本框形状、风格、进度条。"""
    errors = []
    jobs_path, _, _ = _generation_paths(stage)
    path = project / jobs_path
    if not path.is_file():
        return [f"阶段 {stage} 缺少生图任务 {jobs_path}：先按设计稿逐页写好提示词再生成"]
    try:
        jobs = read_json(path).get("jobs") or []
    except (OSError, ValueError, TypeError) as exc:
        return [f"生图任务不可读：{jobs_path}：{exc}"]
    if job_ids is not None:
        jobs = [job for job in jobs if job.get("id") in job_ids]
    if not jobs:
        return [f"阶段 {stage} 没有可自检的生图任务：先按设计稿逐页写好提示词"]
    content = read_json(project / "02_design/content.json")
    slides = content["slides"]
    # A policy update must not retroactively invalidate an immutable human-approved
    # concept snapshot. Any change to jobs or ledger restores all current checks.
    approved_historical_prompts = False
    if stage == "2.1":
        approval_path = project / "03_concepts/approval.json"
        if approval_path.is_file():
            approved = read_json(approval_path)
            bound = approved.get("files") or {}
            approved_historical_prompts = approved.get("kind") == "concept" and all(
                bound.get(name) == digest(project / name)
                for name in ("03_concepts/generation-jobs.json", "03_concepts/generation-ledger.json")
                if (project / name).is_file()
            ) and all(name in bound for name in (
                "03_concepts/generation-jobs.json", "03_concepts/generation-ledger.json"))
    by_id = {slide["id"]: slide for slide in slides}
    order = [slide["id"] for slide in slides]
    progress = content.get("progress_bar") or {}
    excluded = set(progress.get("exclude_page_types") or [])
    enabled = bool(progress.get("enabled", True))
    plan_by_slide = {}
    plan_path = project / "02_design/image-plan.json"
    if plan_path.is_file():
        plan_by_slide = {
            slide["id"]: slide for slide in read_json(plan_path).get("slides", [])
        }
    shapes = {}
    arrows = {}
    spec = project / "02_design/design-spec.md"
    if spec.is_file():
        spec_text = spec.read_text(encoding="utf-8-sig")
        shapes = page_textbox_shapes(spec_text)
        arrows = page_logic_arrows(spec_text)
    for job in jobs:
        label = str(job.get("id") or job.get("asset_id") or "未命名任务")
        prompt = str(job.get("prompt") or "")
        if not prompt.strip():
            errors.append(f"{label} 的提示词为空：生成前先按设计稿逐页写好提示词")
            continue
        page_id = preview_job_page_id(job, order)
        if page_id is None:
            errors.append(f"{label} 缺少有效的本地页面绑定：填写 page_id 或在任务 id 中绑定页面，不要把页面编号写入提示词")
            continue
        leaked = prompt_internal_identifiers(prompt, project_prompt_identifiers(project, job))
        if leaked and not approved_historical_prompts:
            errors.append(f"{label} 的生图提示词包含内部编号：" + "、".join(leaked)
                          + "；改用内容名称与位置描述，编号只留在本地元数据")
        slide = by_id[page_id]
        forbidden = preview_prompt_forbidden_details(
            prompt, [text.get("text") for text in slide.get("texts") or []]
        )
        if forbidden and not approved_historical_prompts:
            errors.append(f"{page_id} 的生图提示词含禁写信息：" + "、".join(forbidden)
                          + "；这些信息只能留在本地设计稿和重建规格，提示词保留内容、框形、分区关系与图片位比例")
        # Box dimensions/height belong to local layout review and reconstruction,
        # not to the AI prompt, per the user's explicit prompt-size prohibition.
        page_type = slide.get("page_type")
        images = ([] if page_type in {"title", "toc"} else
                  list((plan_by_slide.get(page_id) or {}).get("images") or []))
        required_points = [
            label
            for label in POINT_LABELS
            if label != "图片占位框比例" or images
        ]
        if not approved_historical_prompts:
            errors += [f"{page_id}：{message}" for message in prompt_markdown_layout_errors(prompt)]
            errors += [f"{page_id}：{message}" for message in prompt_emphasis_errors(prompt)]
        points = prompt_points(prompt)
        missing_points = [
            label
            for label in required_points
            if not any(point.startswith(label) for point in points)
        ]
        if missing_points:
            errors.append(
                f"{page_id} 的提示词要按Markdown列表写：缺少 "
                + "、".join(missing_points)
                + "；分点顺序为 比例要求／内容要求／排版要求／图片占位框比例／风格要求／进度条要求，"
                "不要把要求揉成一整句"
            )
        if not any(token in prompt for token in CANVAS_RATIO_TOKENS):
            errors.append(
                f"{page_id} 的提示词没有写明整页预览是 16:9 画布（1920×1080）：出图比例要写进提示词"
            )
        if "风格" not in prompt:
            errors.append(
                f"{page_id} 的提示词没有写风格要求：简要写明本页气质、配色及背景／文本框处理，按生图提示词口径展开实际视觉方案"
            )
        if not any(token in prompt for token in PALETTE_MATCH_TOKENS):
            errors.append(
                f"{page_id} 的提示词没有写同风格配色要求："
                "背景与装饰要用与所给 AI 大图相近的颜色（同一套配色）"
            )
        if enabled and page_type not in excluded:
            if "进度条" not in prompt:
                errors.append(
                    f"{page_id} 的提示词没有写进度条要求：条内逐段写出全部小节标题、当前小节突出、分段有色差"
                )
        elif not any(token in prompt for token in NO_PROGRESS_TOKENS):
            errors.append(f"{page_id} 的提示词要写明这一页没有进度条（{page_type} 页不加进度条）")
        for text in slide.get("texts") or []:
            value = str(text.get("text") or "").strip()
            if value and value not in prompt:
                errors.append(
                    f"{page_id} 的提示词没有写明文字 {text.get('id')}：「{value}」："
                    "设计稿里的每段文字都要带进提示词，用于表达内容与语义角色"
                )
        for shape in shapes.get(page_id, []):
            if shape not in prompt:
                errors.append(
                    f"{page_id} 的提示词没有写明文本框形状「{shape}」：文本框形状在风格要求中集中交代，可按已确认意图合理变化"
                )
        if arrows.get(page_id) and not any(token in prompt for token in LOGIC_ARROW_TOKENS):
            errors.append(
                f"{page_id} 的提示词没有写页内逻辑关系：设计稿用箭头／箭形色块表达文字间的逻辑关系，"
                "提示词要写清它们的起止、方向与连接的文字"
            )
        if images and not any(token in prompt for token in RATIO_LOCK_TOKENS):
            errors.append(
                f"{page_id} 的提示词没有强调图片占位框的宽高比不能改变："
                "逐张写清比例后要说明按该比例画、不拉伸、不变形"
            )
        if images and "占位" not in prompt and "placeholder" not in prompt.lower():
            errors.append(
                f"{page_id} 的提示词没有写占位块：计划图片在预览里只画占位块（不写内部编号，默认留空或用简短内容说明）"
            )
        for image in images:
            target = asset_path(project, image.get("path") or "")
            if not target.is_file():
                continue
            with Image.open(target) as opened:
                aspect = opened.width / opened.height
            if not any(token in prompt for token in ratio_tokens(aspect)):
                errors.append(
                    f"{page_id} 的提示词没有写明 {image['id']} 的图片位比例（约 {aspect:.2f}:1）："
                    "占位块要按原件比例画，提示词里逐张写清"
                )
    return list(dict.fromkeys(errors))


def special_split_errors(content, design_spec):
    """Check content-page coverage and a strict majority of all formal pages."""
    eligible = {slide["id"] for slide in content["slides"]
                if slide.get("page_type") == "content"}
    rows = [(page_id, cell) for page_id, cell in page_split_rows(design_spec)
            if page_id in eligible]
    errors = []
    present = {page_id for page_id, cell in rows if cell.strip()}
    for page_id in sorted(eligible - present):
        errors.append(f"{page_id} 的设计稿《页面分块要求》缺少分块方式："
                      "先说明内容逻辑，再选择特殊或常规分块，全篇特殊分块页数须过半")
    ids = [page_id for page_id, _ in rows]
    for page_id in sorted(set(ids)):
        if ids.count(page_id) > 1:
            errors.append(f"{page_id} 的《页面分块要求》重复登记")
    formal_ids = {slide["id"] for slide in content["slides"]}
    special_ids = {
        page_id for page_id, cell in page_split_rows(design_spec)
        if page_id in formal_ids
        and any(entry["kind"] == "special" for entry in split_entries(cell))
    }
    minimum = len(formal_ids) // 2 + 1
    if formal_ids and len(special_ids) < minimum:
        errors.append(
            f"全篇特殊分块页数必须严格大于总页数的一半："
            f"当前 {len(special_ids)}/{len(formal_ids)} 页，至少需要 {minimum} 页；"
            "参考图可按内容调整，不要求照搬，横带与四宫格不计入"
        )
    return errors


# 分区几何以设计稿实际选择为准，不强制照搬参考图。
# 特殊分块的形态词：提示词只写名字不算说明形态，至少要点到一个
SPLIT_FORM_TOKENS = (
    "方向", "倾角", "走向", "弯曲", "凸", "凹", "圆心", "半径", "扇区",
    "波峰", "振幅", "顶点", "出血压边", "条目数", "自上而下", "横向", "竖向", "斜切角度",
)


def split_references_for_page(project, page_id, split_cells=None):
    """该页要用到的分块参考图：[(entry, [项目内相对路径, ...]), ...]。

    形态样例仅供本地设计参考，预览生成不要求向 AI 提供。
    """
    if split_cells is None:
        spec_path = project / "02_design/design-spec.md"
        if not spec_path.is_file():
            return []
        split_cells = dict(page_split_rows(spec_path.read_text(encoding="utf-8-sig")))
    content = read_json(project / "02_design/content.json")
    page_type = {slide["id"]: slide.get("page_type") for slide in content["slides"]}
    if page_type.get(page_id) in (None, "title", "toc", "thanks"):
        return []
    entries = split_entries(split_cells.get(page_id, ""))
    return [
        (
            entry,
            [f"{SPLIT_REFERENCE_ROOT}/{entry['id']}/{name}" for name in entry["files"]],
        )
        for entry in entries
    ]


def split_reference_manifest_errors(project, split_cells):
    """Compatibility hook: split images are local design aids, not preview inputs."""
    return []


def image_plan_trace_errors(project, image_plan=None):
    """Require the final image plan to preserve the 1.2 image intent."""
    errors = []
    intent_path = project / "02_design/image-intent-plan.json"
    try:
        intent = read_json(intent_path)
    except (OSError, ValueError, TypeError) as exc:
        return [f"图片意图不可用，无法核对精确计划：{exc}"]
    errors += schema_errors(intent, "image-intent-plan")
    if image_plan is None:
        try:
            image_plan = read_json(project / "02_design/image-plan.json")
        except (OSError, ValueError, TypeError) as exc:
            return errors + [f"精确图片计划不可用：{exc}"]
    errors += schema_errors(image_plan, "image-plan")
    if errors:
        return errors
    intent_slides = {slide["id"]: slide for slide in intent["slides"]}
    plan_slides = {slide["id"]: slide for slide in image_plan["slides"]}
    if [slide["id"] for slide in image_plan["slides"]] != [slide["id"] for slide in intent["slides"]]:
        errors.append("精确图片计划的页面编号或顺序与阶段 1.2 图片意图不一致")
    for slide_id, intended in intent_slides.items():
        planned = plan_slides.get(slide_id)
        if not planned:
            continue
        expected_ids = [image["id"] for image in intended["images"]]
        planned_ids = [image["id"] for image in planned["images"]]
        if planned_ids != expected_ids:
            errors.append(f"{slide_id} 的精确图片编号或顺序与阶段 1.2 图片意图不一致")
            continue
        intended_by_id = {image["id"]: image for image in intended["images"]}
        for image in planned["images"]:
            source = intended_by_id[image["id"]]
            if image["sourceId"] != source["sourceId"]:
                errors.append(f"{image['id']} 的 sourceId 与阶段 1.2 图片意图不一致")
            if image["description"] != source["description"]:
                errors.append(f"{image['id']} 的图片内容描述与阶段 1.2 图片意图不一致")
            if source.get("plannedPath") and image["path"] != source["plannedPath"]:
                errors.append(f"{image['id']} 的 path 与阶段 1.2 计划路径不一致")
    return errors


def image_plan_geometry_errors(image_plan):
    errors = []
    for slide in image_plan.get("slides", []):
        for image in slide.get("images", []):
            box = image.get("box", {})
            x, y, w, h = box.get("x"), box.get("y"), box.get("w"), box.get("h")
            if all(isinstance(value, (int, float)) for value in (x, y, w, h)):
                if x + w > 1.0000001 or y + h > 1.0000001:
                    errors.append(f"{image.get('id', '未命名图片')} 的归一化位置超出 1920x1080 画布")
                expected = normalized_box_to_px(box)
                if image.get("pixelBox") != expected:
                    errors.append(f"{image.get('id', '未命名图片')} 的 pixelBox 与归一化 box 在当前 1920x1080 画布上不一致")
            crop = image.get("crop")
            if crop:
                cx, cy = crop.get("x"), crop.get("y")
                cw, ch = crop.get("width"), crop.get("height")
                if all(isinstance(value, (int, float)) for value in (cx, cy, cw, ch)):
                    if cx + cw > 1.0000001 or cy + ch > 1.0000001:
                        errors.append(f"{image.get('id', '未命名图片')} 的 crop 区域超出原图边界")
    return errors


def ai_image_config_errors(project, require_ready=True):
    """Validate the user-approved provider configuration without reading secrets."""
    path = project / "00_intake/ai-image-config.json"
    try:
        config = read_json(path)
    except (OSError, ValueError, TypeError) as exc:
        return [f"缺少或无效的 AI 生图配置：{exc}"]
    errors = schema_errors(config, "ai-image-config")
    if errors:
        return errors
    if require_ready and not config["credentialsReady"]:
        errors.append("内置生图工具尚未标记为就绪；阶段1.1须确认工具可用性" if config.get("provider") == "imagegen" else "AI 生图凭据尚未标记为就绪；阶段 1.1 必须先向用户确认")
    try:
        resolve_script(config)
    except (OSError, ValueError, TypeError) as exc:
        errors.append(f"AI 生图适配脚本不可用：{exc}")
    return errors


def _sensitive_ledger_errors(value, path=""):
    """Reject raw prompts, credentials and service URLs from the evidence ledger."""
    errors = []
    sensitive_keys = {
        "prompt",
        "api_key",
        "apikey",
        "authorization",
        "signed_url",
        "url",
        "token",
        "secret",
    }
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}/{key}" if path else key
            if str(key).lower() in sensitive_keys:
                errors.append(f"账本不得保存敏感字段：{child_path}")
            errors += _sensitive_ledger_errors(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            errors += _sensitive_ledger_errors(child, f"{path}/{index}")
    elif isinstance(value, str):
        lowered = value.lower()
        if "http://" in lowered or "https://" in lowered or "bearer " in lowered:
            errors.append(f"账本不得保存服务 URL 或凭据：{path or '/'}")
    return errors


def generation_paths(stage):
    """Where a generation stage keeps its jobs, ledger and normalized outputs."""
    locations = {
        "1.2": (
            "02_design/generation-jobs.json",
            "02_design/generation-ledger.json",
            "02_design/generated-assets",
        ),
        "2.1": (
            "03_concepts/generation-jobs.json",
            "03_concepts/generation-ledger.json",
            "03_concepts/assets",
        ),
        "2.2": (
            "04_full-preview/generation-jobs.json",
            "04_full-preview/generation-ledger.json",
            "04_full-preview/assets",
        ),
    }
    if stage not in locations:
        raise ValueError(f"不支持的生图阶段：{stage}")
    return locations[stage]


_generation_paths = generation_paths


INTERNAL_REFERENCE_PREFIXES = (
    "02_design/split-references/",
    "03_concepts/",
    "04_full-preview/",
)


def internal_reference(project, reference):
    """Project-internal AI artifacts (split references, earlier previews) may be reused as references."""
    text = str(reference or "").replace("\\", "/").lstrip("./")
    if not any(text.startswith(prefix) for prefix in INTERNAL_REFERENCE_PREFIXES):
        return False
    try:
        candidate = (project / text).resolve()
    except OSError:
        return False
    return candidate.is_file() and candidate.is_relative_to(project.resolve())


PROMPTS_LOG = "02_design/generation-prompts.md"


def generation_prompts_errors(project, stage):
    """Every AI image prompt must be written into the shared prompts log."""
    path = project / PROMPTS_LOG
    if not path.is_file():
        return [
            f"缺少生图提示词记录 {PROMPTS_LOG}：所有阶段的提示词都要集中记录在这个文件里"
        ]
    try:
        logged = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        return [f"生图提示词记录不可读：{PROMPTS_LOG}：{exc}"]
    try:
        jobs_path, _, _ = _generation_paths(stage)
    except ValueError as exc:
        return [str(exc)]
    if not (project / jobs_path).is_file():
        return []
    jobs = read_json(project / jobs_path).get("jobs", [])
    errors = []
    if f"## 阶段 {stage}" not in logged:
        errors.append(
            f"生图提示词记录缺少「## 阶段 {stage}」小节：每个阶段的任务提示词都要写进 {PROMPTS_LOG}"
        )
    for job in jobs:
        if job.get("id") and job["id"] not in logged:
            errors.append(
                f"{PROMPTS_LOG} 没有记录生图任务 {job['id']}：每轮生成后都要登记 id、"
                "素材编号、用途、参考图与提示词全文"
            )
    return errors


def generation_jobs_errors(project, stage, config=None):
    """Validate jobs against the provider, model, reference and edit contract."""
    jobs_path, _, output_root = _generation_paths(stage)
    try:
        plan = read_json(project / jobs_path)
    except (OSError, ValueError, TypeError) as exc:
        return [f"缺少或无效的生图任务清单：{jobs_path}：{exc}"]
    errors = schema_errors(plan, "generation-job")
    if errors:
        return errors
    if config is None:
        try:
            config = read_json(project / "00_intake/ai-image-config.json")
        except (OSError, ValueError, TypeError) as exc:
            return [f"AI 生图配置不可用：{exc}"]
    material_by_id = {}
    try:
        material_by_id = {
            item["id"]: item
            for item in read_json(project / "01_inventory/materials.json")["materials"]
        }
    except (OSError, ValueError, TypeError, KeyError):
        pass
    identifiers = set()
    asset_ids = set()
    outputs = set()
    root = (project / output_root).resolve()
    stage_asset_ids = {
        value.get("asset_id") for value in plan["jobs"] if isinstance(value, dict)
    }
    for job in plan["jobs"]:
        identifier = job["id"]
        leaked = prompt_internal_identifiers(str(job.get("prompt") or ""), project_prompt_identifiers(project, job))
        if leaked:
            errors.append(f"{identifier} 的生图提示词包含内部编号：" + "、".join(leaked)
                          + "；先改为内容名称与位置描述再生成")
        if stage in {"2.1", "2.2"}:
            if job.get("asset_mode", "strict") != "strict":
                errors.append(f"{identifier} 的整页预览必须使用 strict；不得用 crop 或 pad 修正比例")
            width, height = map(int, job.get("size", "1920x1080").split("x"))
            if width * 9 != height * 16:
                errors.append(f"{identifier} 的整页请求尺寸不是精确 16:9：{width}x{height}，退回")
        if identifier in identifiers:
            errors.append(f"重复生图任务：{identifier}")
        identifiers.add(identifier)
        asset_id = job["asset_id"]
        if asset_id in asset_ids:
            errors.append(f"重复生成素材编号：{asset_id}")
        asset_ids.add(asset_id)
        if job.get("model") and job["model"] != config.get("model"):
            errors.append(
                f"{identifier} 的任务模型 {job['model']} "
                f"与配置模型 {config.get('model')} 不一致"
            )
        output = Path(job["output"])
        resolved = (project / output).resolve()
        expected_output = f"{output_root}/{asset_id}.png"
        if (
            output.is_absolute()
            or output.suffix.lower() != ".png"
            or not resolved.is_relative_to(root)
        ):
            errors.append(f"{identifier} 的输出必须位于 {output_root} 内并以 .png 结尾")
        elif output.as_posix() != expected_output:
            errors.append(
                f"{identifier} 的输出必须是稳定路径 {expected_output}；"
                "不得以整页方案图或页面编号作为 AI 输出"
            )
        relative = (
            resolved.relative_to(project).as_posix()
            if resolved.is_relative_to(project)
            else job["output"]
        )
        if relative in outputs:
            errors.append(f"重复生图输出路径：{relative}")
        outputs.add(relative)
        references = job.get("references", [])
        limit = config.get("referenceImageLimit", 0)
        uploaded = [item for item in references if not internal_reference(project, item)]
        if len(uploaded) > limit:
            errors.append(f"{identifier} 的参考图数量超过用户确认上限 {limit}")
        if uploaded and config.get("allowReferenceUpload") is not True:
            errors.append(f"{identifier} 使用外部参考图，但用户未允许上传参考图")
        for reference_id in references:
            if internal_reference(project, reference_id):
                if not (project / reference_id).is_file():
                    errors.append(f"{identifier} 的参考图不存在：{reference_id}")
                continue
            item = material_by_id.get(reference_id)
            if not item:
                errors.append(f"{identifier} 引用了未登记材料：{reference_id}")
            elif item.get("externalUpload") is not True:
                errors.append(f"{identifier} 的材料未获准上传：{reference_id}")
        edit_source = job.get("edit_source")
        if isinstance(edit_source, dict):
            edited_asset = edit_source.get("assetId", "")
            if edited_asset == asset_id:
                errors.append(f"{identifier} 的 edit_source 不能指向自身输出：{asset_id}")
            elif edited_asset not in stage_asset_ids:
                errors.append(
                    f"{identifier} 的 edit_source 必须指向本阶段已登记的 GEN 素材：{edited_asset}"
                )
            expected_edit = f"{output_root}/{edited_asset}.png"
            if Path(edit_source.get("path", "")).as_posix() != expected_edit:
                errors.append(
                    f"{identifier} 的 edit_source 路径必须是本阶段稳定路径 {expected_edit}"
                )
            elif not (project / expected_edit).is_file():
                errors.append(f"{identifier} 的被编辑素材尚不存在：{expected_edit}")
            if config.get("allowReferenceUpload") is not True:
                errors.append(f"{identifier} 使用生图编辑，但用户未允许上传参考图")
            if len(references) + 1 > limit:
                errors.append(
                    f"{identifier} 的参考图与生图编辑输入合计超过用户确认上限 {limit}"
                )
        if not isinstance(job.get("intended_use"), str) or not job["intended_use"].strip():
            errors.append(f"{identifier} 必须说明素材 intended_use")
        if not isinstance(job.get("factual_boundary"), str) or not job["factual_boundary"].strip():
            errors.append(f"{identifier} 必须说明素材 factual_boundary")
        if stage == "1.2":
            purpose = f"{identifier} {job.get('intended_use') or ''}"
            if any(token in purpose for token in BIG_IMAGE_JOB_TOKENS):
                prompt = str(job.get("prompt") or "")
                if not any(token in prompt for token in CANVAS_RATIO_TOKENS):
                    errors.append(
                        f"{identifier} 的大图提示词没有写明比例 16:9："
                        "封面大图／目录页大图／背景底图都要按 16:9 横版生成，"
                        "提示词里写清 16:9（1920×1080）"
                    )
    return errors


def generation_ledger_errors(project, stage, config=None, jobs=None):
    """Require one traceable successful API call for every configured job."""
    jobs_path, ledger_path, _ = _generation_paths(stage)
    try:
        ledger = read_json(project / ledger_path)
    except (OSError, ValueError, TypeError) as exc:
        return [f"缺少或无效的生图账本：{ledger_path}：{exc}"]
    errors = schema_errors(ledger, "generation-ledger")
    if errors:
        return errors
    if ledger["stage"] != stage:
        errors.append(f"生图账本阶段 {ledger['stage']} 与 {stage} 不一致")
    if config is None:
        try:
            config = read_json(project / "00_intake/ai-image-config.json")
        except (OSError, ValueError, TypeError) as exc:
            return [f"AI 生图配置不可用：{exc}"]
    if jobs is None:
        try:
            jobs = read_json(project / jobs_path)
        except (OSError, ValueError, TypeError) as exc:
            return [f"生图任务清单不可用：{exc}"]
    if ledger["provider"] != config.get("provider"):
        errors.append(
            f"生图账本供应商 {ledger['provider']} "
            f"与配置 {config.get('provider')} 不一致"
        )
    if ledger["model"] != config.get("model"):
        errors.append(
            f"生图账本模型 {ledger['model']} 与配置 {config.get('model')} 不一致"
        )
    try:
        adapter_script = resolve_script(config)
        adapter_hash = digest(adapter_script)
    except (OSError, ValueError, TypeError) as exc:
        errors.append(f"无法验证生图适配脚本：{exc}")
        adapter_hash = None
    request_ids = set()
    for job in jobs["jobs"]:
        identifier = job["id"]
        record = ledger["jobs"].get(identifier)
        if not record:
            errors.append(f"生图任务缺少账本记录：{identifier}")
            continue
        if record["status"] != "complete":
            errors.append(f"生图任务没有成功完成：{identifier}")
            continue
        if record.get("provider") != config.get("provider"):
            errors.append(f"{identifier} 账本供应商与配置不一致")
        if record.get("model") != config.get("model"):
            errors.append(f"{identifier} 账本模型与配置不一致")
        request_id = (record.get("tool_call_id") or (record.get("tool_result_id"), record.get("raw_sha256"))) if config.get("provider") == "imagegen" else record.get("request_id")
        if request_id in request_ids:
            errors.append(f"{identifier} 的生成调用编号与其他任务重复")
        request_ids.add(request_id)
        if config.get("provider") == "imagegen":
            from builtin_imagegen import receipt_errors
            errors += receipt_errors(project, job, record)
        expected_prompt_hash = hashlib.sha256(job["prompt"].encode("utf-8")).hexdigest()
        if record.get("prompt_sha256") != expected_prompt_hash:
            errors.append(f"{identifier} 的提示词哈希与当前任务不一致")
        if adapter_hash and record.get("adapter_script_sha256") != adapter_hash:
            errors.append(f"{identifier} 的适配脚本哈希与当前配置不一致")
        if record.get("output") != job["output"]:
            errors.append(f"{identifier} 的账本输出与任务路径不一致")
        if record.get("references", []) != job.get("references", []):
            errors.append(f"{identifier} 的参考图记录与任务不一致")
        raw_path = asset_path(project, record.get("raw_path", ""))
        output_path = asset_path(project, record.get("output", ""))
        raw_value = record.get("raw_path", "")
        if (
            Path(raw_value).is_absolute()
            or not raw_path.resolve().is_relative_to(project.resolve())
            or "raw" not in raw_path.parts
        ):
            errors.append(f"{identifier} 的原始生成图路径必须位于项目 raw 目录内")
        if not raw_path.is_file():
            errors.append(f"{identifier} 缺少保留的原始生成图：{record.get('raw_path')}")
        elif digest(raw_path) != record.get("raw_sha256"):
            errors.append(f"{identifier} 的原始生成图哈希已变化")
        if stage in {"2.1", "2.2"} and raw_path.is_file():
            try:
                with Image.open(raw_path) as raw_image:
                    if raw_image.width * 9 != raw_image.height * 16:
                        errors.append(f"{identifier} 的实际供应商原图不是精确 16:9，退回")
                    if record.get("normalization", {}).get("original_size") != list(raw_image.size):
                        errors.append(f"{identifier} 的原图尺寸记录与实际文件不一致")
            except (OSError, ValueError):
                errors.append(f"{identifier} 的原始生成图无法解码")
        if not output_path.is_file():
            errors.append(f"{identifier} 缺少规范化输出：{record.get('output')}")
        else:
            if digest(output_path) != record.get("sha256"):
                errors.append(f"{identifier} 的规范化输出哈希已变化")
            errors += [f"{identifier}: {message}" for message in asset_image_errors(output_path)]
        normalization = record.get("normalization", {})
        output_size = normalization.get("output_size")
        original_size = normalization.get("original_size")
        if (
            not isinstance(output_size, list)
            or len(output_size) != 2
            or not all(isinstance(value, int) and value > 0 for value in output_size)
        ):
            errors.append(f"{identifier} 缺少有效的素材规范化尺寸记录")
        whole_page = stage in {"2.1", "2.2"}
        mode = normalization.get("mode")
        valid_modes = (
            {"proportional_resize"} if whole_page else {"preserve", "pad", "crop"}
        )
        if mode not in valid_modes:
            errors.append(f"{identifier} 的素材规范化模式无效")
        elif whole_page:
            if (not isinstance(original_size, list) or len(original_size) != 2
                    or not all(type(v) is int and v > 0 for v in original_size)
                    or original_size[0] * 9 != original_size[1] * 16):
                errors.append(f"{identifier} 的供应商原图不是精确 16:9，退回；不得以补边或裁切输出代替")
            if output_size != [1920, 1080]:
                errors.append(f"{identifier} 的整页预览必须规范化为精确 1920x1080")
        else:
            if mode != job.get("asset_mode", "preserve"):
                errors.append(f"{identifier} 的素材规范化模式与任务不一致")
            if mode == "preserve" and output_size != original_size:
                errors.append(f"{identifier} 使用 preserve 时不得改变供应商原始尺寸")
            if mode in {"pad", "crop"} and output_size != job.get("asset_size"):
                errors.append(f"{identifier} 的规范化尺寸与 asset_size 不一致")
        if not 1 <= record["attempts"] <= job.get("max_attempts", 8):
            errors.append(f"{identifier} 的尝试次数超过单任务上限")
    errors += _sensitive_ledger_errors(ledger)
    return errors


def _preview_pages_path(project, stage, option=None):
    if stage == "2.1":
        return project / f"03_concepts/option-{option}/preview.json"
    return project / "04_full-preview/previews.json"


def read_preview_pages(project, stage, option=None):
    path = _preview_pages_path(project, stage, option)
    if not path.is_file():
        return None
    try:
        return read_json(path)
    except (OSError, ValueError, TypeError):
        return None



def placeholder_errors(project, page, plan, job, page_type=None):
    """阶段 2.1／2.2：计划图片先在原位画占位块，比例与要插入的图片一致。"""
    if page_type in {"title", "toc"}:
        return []
    errors = []
    images = list((plan or {}).get("images") or [])
    if not images:
        return errors
    listed = {
        item.get("imageId"): item
        for item in (page.get("placeholders") or [])
        if isinstance(item, dict)
    }
    prompt = str((job or {}).get("prompt") or "")
    if "占位" not in prompt and "placeholder" not in prompt.lower():
        errors.append(
            f"{page['id']} 的生图任务提示词没有写占位块：计划图片在预览里只画占位块（不写内部编号，默认留空或用简短内容说明），"
            "2.1 保留占位，2.2 批准前本地插入登记原件，3.3 独立组装同一原件"
        )
    file = project / page["file"]
    for image in images:
        entry = listed.get(image["id"])
        if entry is None:
            errors.append(
                f"{page['id']} 没有登记 {image['id']} 的占位块：预览里先在计划位置画占位块，"
                "并在预览清单的 placeholders 里记录它的框"
            )
            continue
        box = entry.get("box") or {}
        planned = image.get("box") or {}
        if any(
            not isinstance(box.get(key), (int, float))
            or abs(box[key] - planned.get(key, 0)) > PLACEHOLDER_BOX_TOLERANCE
            for key in ("x", "y")
        ):
            errors.append(
                f"{page['id']} 的 {image['id']} 占位块位置与图片计划不一致："
                f"占位块 {box}，计划 {planned}"
            )
            continue
        if any(
            not isinstance(box.get(key), (int, float))
            or abs(box[key] - planned.get(key, 0)) > PLACEHOLDER_BOX_TOLERANCE
            for key in ("w", "h")
        ):
            errors.append(
                f"{page['id']} 的 {image['id']} 占位块大小与图片计划不一致："
                f"占位块 {box}，计划 {planned}"
            )
        target = asset_path(project, image.get("path") or "")
        if not target.is_file():
            continue
        with Image.open(target) as opened:
            aspect = opened.width / opened.height
        box_aspect = (box["w"] * 1920) / (box["h"] * 1080)
        aspect_review = entry.get("aspectReview") or {}
        attempts = aspect_review.get("revisionAttempts")
        reviewed = (
            type(attempts) is int and attempts >= 2
            and isinstance(aspect_review.get("note"), str)
            and bool(aspect_review["note"].strip())
        )
        tolerance = (PHOTO_FRAME_ASPECT_RELAXED_TOLERANCE if reviewed
                     else PHOTO_FRAME_ASPECT_TOLERANCE)
        if abs(box_aspect - aspect) / aspect > tolerance:
            errors.append(
                f"{page['id']} 的 {image['id']} 占位块比例 {box_aspect:.2f} 与要插入的图片 "
                f"{aspect:.2f} 不一致（相差超过 {tolerance:.0%}）："
                "占位块要按计划图片的比例预留，组装时才能原位放回"
            )
    return errors


def design_errors(project):
    """阶段 1.3：设计稿、内容清单与素材登记的完整性与一致性。"""
    errors = []
    content = read_json(project / "02_design/content.json")
    errors += schema_errors(content, "content")
    errors += reference_category_errors(content)
    generated_assets = read_json(project / "02_design/generated-assets.json")
    errors += schema_errors(generated_assets, "generated-assets")
    image_intent = read_json(project / "02_design/image-intent-plan.json")
    errors += schema_errors(image_intent, "image-intent-plan")
    claim_map = read_json(project / "02_design/claim-map.json")
    errors += schema_errors(claim_map, "claim-map")
    if errors:
        return errors
    slide_ids = [slide["id"] for slide in content["slides"]]
    if [slide["id"] for slide in image_intent["slides"]] != slide_ids:
        errors.append("图片计划的页面编号或顺序与 content.json 不一致")
    if [slide["id"] for slide in claim_map["slides"]] != slide_ids:
        errors.append("结论映射的页面编号或顺序与 content.json 不一致")
    if not content["slides"] or content["slides"][0]["page_type"] != "title":
        errors.append("第一页必须是 title 标题页")
    toc_indexes = [
        index for index, slide in enumerate(content["slides"]) if slide["page_type"] == "toc"
    ]
    if content["include_toc"]:
        if toc_indexes != [1]:
            errors.append("用户要求目录时，第二页必须是唯一的 toc 目录页")
    elif toc_indexes:
        errors.append("用户不需要目录时，content.json 不得包含 toc 页面")
    progress = content["progress_bar"]
    if "title" not in progress["exclude_page_types"]:
        errors.append("顶部进度条必须排除 title 标题页")
    if content["include_toc"] and "toc" not in progress["exclude_page_types"]:
        errors.append("存在目录页时，顶部进度条必须排除 toc 目录页")
    if content.get("include_thanks") and "thanks" not in progress["exclude_page_types"]:
        errors.append("存在致谢页时，顶部进度条必须排除 thanks 致谢页")
    sections = content.get("sections") or []
    section_ids = [section["id"] for section in sections]
    if len(section_ids) != len(set(section_ids)):
        errors.append("sections 包含重复小节编号")
    titles = [section["title"] for section in sections]
    if len(titles) != len(set(titles)):
        errors.append("sections 的小节标题必须互不重复，进度条内需要逐字显示")
    excluded = set(progress.get("exclude_page_types") or [])
    eligible_ids = [
        slide["id"] for slide in content["slides"] if slide.get("page_type") not in excluded
    ]
    covered = [slide_id for section in sections for slide_id in section["slide_ids"]]
    unknown = sorted(set(covered) - set(eligible_ids))
    if unknown:
        errors.append(f"sections 引用了不合格页面（标题页、目录页或不存在）：{unknown}")
    missing = sorted(set(eligible_ids) - set(covered))
    if missing:
        errors.append(f"sections 未覆盖启用进度条的全部合格页面：{missing}")
    repeated = sorted({value for value in covered if covered.count(value) > 1})
    if repeated:
        errors.append(f"sections 中同一页面只能属于一个小节：{repeated}")
    if content["include_toc"]:
        toc = next(
            (slide for slide in content["slides"] if slide["page_type"] == "toc"), None
        )
        entries = []
        if toc:
            entries.append(toc["title"])
            entries.extend(text["text"] for text in toc["texts"])
        for section in sections:
            title = section["title"].strip()
            if not any(title and title in entry for entry in entries):
                errors.append(
                    f"小节标题“{title}”必须逐字出现在目录页条目中；"
                    "进度条条内文字与目录页必须一致"
                )
    design_spec = (project / "02_design/design-spec.md").read_text(encoding="utf-8-sig")
    errors += design_page_plan_errors(content, design_spec)
    plan_section = design_spec.split("## 逐页规划", 1)[-1].split("## 内容来源与脚注", 1)[0]
    pages = [page for page in re.split(r"^### ", plan_section, flags=re.M)[1:]]
    if not pages:
        errors.append("设计稿的《逐页规划》没有逐页小节（每页以 `### Sxx：标题` 开头）")
    for page in pages:
        page_id = page.split("：", 1)[0].strip() or "未命名页面"
        if "**风格要求：**" not in design_spec.split("## 逐页规划", 1)[0] and "文本框：" not in page:
            errors.append(
                f"{page_id} 的排版分级没有写明文本框形状：单段文字写「文本框：<形状>」，"
                "并列文本段落写明整组统一的形状，没有文本框就写「无文本框：文字直接排在画面上」"
            )
        if ("图像框：" not in page and "（图片" not in page and "无图片" not in page
                and "原底图" not in page):
            errors.append(
                f"{page_id} 的排版分级没有写清插入图片的图像框：写「图像框：位置＋比例」，"
                "没有图片就写「无图片」"
            )
    if "分块方式" not in plan_section:
        errors.append(
            "设计稿的逐页规划必须按《排版分级写法》写「分块方式」："
            "分块方式 → 各分块 → 分块上部／下部／左部／右部／分块内 → 并列文本逐条"
        )
    if "待填写" in plan_section:
        errors.append(
            "设计稿的逐页规划不得残留占位文字「待填写」：每页都要写入实际内容与最终上屏文字"
        )
    errors += special_split_errors(content, design_spec)
    if "三种设计风格" not in design_spec:
        errors.append(
            "设计稿必须写明「三种设计风格」（方向 a／b／c）：宏观结构、三种风格与阶段 1 的 PPT 要求"
            "是设计稿的开头部分，并要与阶段 2.1 的 option-a/b/c 和候选图的 styleId 对应"
        )
    for heading in (
        "## 全篇叙述逻辑链",
        "## 目录要求",
        "## 致谢页要求",
        "## 演讲稿要求",
        "## 顶部进度条要求",
        "## 页面分块要求",
        "## 文本框、要点拆分与装饰色系要求",
        "## 背景底图与内容页补图要求",
        "## 待补充材料",
    ):
        if heading not in design_spec:
            errors.append(f"设计稿必须提供独立章节：{heading}")
    image_by_slide = {
        slide["id"]: {image["id"] for image in slide["images"]} for slide in image_intent["slides"]
    }
    for slide in image_intent["slides"]:
        image_ids = [image["id"] for image in slide["images"]]
        if len(image_ids) != len(set(image_ids)):
            errors.append(f"{slide['id']} 的图片意图包含重复图片编号")
    material_ids = {
        item["id"] for item in read_json(project / "01_inventory/materials.json")["materials"]
    }
    generated_ids = [asset.get("id") for asset in generated_assets.get("assets", [])]
    if len(generated_ids) != len(set(generated_ids)):
        errors.append("生成素材清单包含重复编号")
    generated_by_id = {asset.get("id"): asset for asset in generated_assets.get("assets", [])}
    for asset in generated_assets.get("assets", []):
        identifier = asset.get("id", "未命名生成素材")
        path = asset.get("path")
        sha256 = asset.get("sha256")
        if path and sha256:
            errors += check_hashes(project, {path: sha256})
        for source_id in asset.get("sourceReferences", []):
            if source_id not in material_ids:
                errors.append(f"{identifier} 引用了未登记参考材料：{source_id}")
    for slide in image_intent["slides"]:
        for image in slide["images"]:
            if image["sourceId"] not in material_ids and not image["sourceId"].startswith("GEN-"):
                errors.append(f"{image['id']} 引用了未登记来源：{image['sourceId']}")
            if image["sourceId"].startswith("GEN-") and image["sourceId"] not in generated_by_id:
                errors.append(f"{image['id']} 引用了未登记生成素材：{image['sourceId']}")
    for slide in content["slides"]:
        if not set(slide["materials"]).issubset(material_ids):
            errors.append(f"{slide['id']} 引用了未登记材料")
    text_ids = {text["id"] for slide in content["slides"] for text in slide["texts"]}
    for slide in claim_map["slides"]:
        for claim in slide["claims"]:
            if not set(claim["sourceIds"]).issubset(material_ids):
                errors.append(f"{claim['id']} 引用了未登记材料")
            if not set(claim["elementIds"]).issubset(text_ids):
                errors.append(f"{claim['id']} 引用了不存在的文本元素")
            if not set(claim.get("imageIds", [])).issubset(image_by_slide.get(slide["id"], set())):
                errors.append(f"{claim['id']} 引用了本页不存在的图片元素")
    return errors


def preview_pages_errors(project, stage, option=None):
    """Stage 2.1/2.2: AI whole-page previews following the design spec and split references."""
    path = _preview_pages_path(project, stage, option)
    relative = path.relative_to(project).as_posix()
    if not path.is_file():
        return [
            f"阶段 {stage} 缺少整页预览清单 {relative}："
            "每一页都要用 AI 按设计稿生成整页预览，并逐页登记来源"
        ]
    try:
        preview = read_json(path)
        errors = schema_errors(preview, "preview-pages")
    except (OSError, ValueError, TypeError) as exc:
        return [f"整页预览清单不可读：{relative}：{exc}"]
    if errors:
        return errors
    if preview["stage"] != stage:
        errors.append(f"整页预览清单记录的是阶段 {preview['stage']}，与 {stage} 不一致")
    if stage == "2.1" and preview.get("option") != option:
        errors.append(f"整页预览清单记录的是方案 {preview.get('option')}，与 {option} 不一致")
    content = read_json(project / "02_design/content.json")
    design_spec = project / "02_design/design-spec.md"
    split_cells = {}
    if design_spec.is_file():
        split_cells = dict(page_split_rows(design_spec.read_text(encoding="utf-8-sig")))
    plan_by_slide = {}
    plan_path = project / "02_design/image-plan.json"
    if plan_path.is_file():
        plan_by_slide = {
            slide["id"]: slide for slide in read_json(plan_path).get("slides", [])
        }
    jobs_path, ledger_path, _ = _generation_paths(stage)
    ledger = {}
    if (project / ledger_path).is_file():
        try:
            ledger = read_json(project / ledger_path).get("jobs", {})
        except (OSError, ValueError, TypeError):
            ledger = {}
    jobs = {}
    if (project / jobs_path).is_file():
        try:
            jobs = {
                job["id"]: job for job in read_json(project / jobs_path).get("jobs", [])
            }
        except (OSError, ValueError, TypeError, KeyError):
            jobs = {}
    page_ids = [page["id"] for page in preview["pages"]]
    if len(page_ids) != len(set(page_ids)):
        errors.append("整页预览清单包含重复页面编号")
    content_ids = [slide["id"] for slide in content["slides"]]
    page_type = {slide["id"]: slide.get("page_type") for slide in content["slides"]}
    if stage == "2.1":
        if not 1 <= len(page_ids) <= 3:
            errors.append("阶段 2.1 的每个方案要有 1 至 3 页整页预览")
        expected = [content_ids[0]] if content_ids else []
        toc = [sid for sid in content_ids if page_type.get(sid) == "toc"]
        if toc:
            expected.append(toc[0])
        body_pages = [sid for sid in content_ids if page_type.get(sid) == "content"]
        missing = [sid for sid in expected if sid not in page_ids]
        if missing:
            errors.append(
                f"阶段 2.1 的代表页缺少：{'、'.join(missing)}（至少要封面页；存在目录页时也要有目录页）"
            )
        if body_pages and not any(sid in page_ids for sid in body_pages):
            errors.append(
                "阶段 2.1 至少要有一页内容页代表页（内容页任选一页，优先挑信息量最大、"
                "版式最复杂的一页；不限定第一页）"
            )
        extra = [sid for sid in page_ids if sid not in content_ids]
        if extra:
            errors.append(f"整页预览包含设计稿之外的页面：{'、'.join(extra)}")
    else:
        if page_ids != content_ids:
            errors.append("阶段 2.2 的整页预览必须覆盖全部定稿页面且顺序一致")
        if not str(preview.get("styleConstraints") or "").strip():
            errors.append(
                "阶段 2.2 的整页预览清单要写明 styleConstraints："
                "选定风格写进设计稿后，AI 生图按它统一全篇"
            )
    errors += split_reference_manifest_errors(project, split_cells)
    for page in preview["pages"]:
        file = project / page["file"]
        if not file.is_file():
            errors.append(f"{page['id']} 缺少整页预览：{page['file']}")
            continue
        errors += image_errors(file)
        if digest(file) != page["sha256"]:
            errors.append(f"{page['id']} 的整页预览哈希已变化：{page['file']}")
        is_title = page_type.get(page["id"]) == "title"
        job = jobs.get(page["jobId"])
        record = ledger.get(page["jobId"])
        if job is None or record is None:
            errors.append(
                f"{page['id']} 的整页预览任务 {page['jobId']} 没有生图任务或账本记录"
            )
            continue
        if record.get("status") != "complete":
            errors.append(f"{page['id']} 的整页预览任务 {page['jobId']} 尚未成功完成")
        elif record.get("sha256") != (page.get("providerSha256") if stage == "2.2" or page.get("localPlaceholderRepairs") else page["sha256"]):
            errors.append(
                f"{page['id']} 的整页预览与账本记录的哈希不一致：{page['file']}"
                "（阶段 2.1 核对预览；阶段 2.2 核对插图前的 AI 原始页）"
            )
        elif record.get("output") and not (project / record["output"]).is_file():
            errors.append(f"{page['id']} 的整页预览原始输出已缺失：{record['output']}")
        prompt = str(job.get("prompt") or "")
        if preview_job_page_id(job, {slide["id"] for slide in content["slides"]}) != page["id"]:
            errors.append(f"{page['id']} 的生图任务本地页面绑定不一致：核对 page_id／任务 id，不在提示词中写内部编号")
        if not str(page.get("promptSummary") or "").strip():
            errors.append(
                f"{page['id']} 的整页预览缺少 promptSummary："
                "要写明这一页用了设计稿的哪些分块、文字层级与图片位"
            )
        prompt_lower = prompt.lower()
        if not any(token in prompt_lower for token in ("文本框", "text box", "textbox")):
            errors.append(
                f"{page['id']} 的生图任务提示词没有写文本框：文本框形状与配色在风格要求中集中说明，"
                "或写明「无文本框」"
            )
        cell = split_cells.get(page["id"], "")
        if prompt and cell:
            for entry in [item for item in split_entries(cell) if item["kind"] == "special"]:
                tokens = [entry["name"], entry["label"]] + list(entry.get("aliases") or [])
                if not any(token and token in prompt for token in tokens):
                    errors.append(
                        f"{page['id']} 的整页预览提示词没有写明特殊分块（{entry['label']}）："
                        "预览要按设计稿画出分块"
                    )
                elif not (
                    any(word in prompt for word in SPLIT_FORM_TOKENS)
                    or (
                        entry["id"] == "honeycomb"
                        and all(word in prompt for word in (
                            "三个六边形", "交错", "上方居中", "下方左右"
                        ))
                    )
                ):
                    errors.append(
                        f"{page['id']} 的整页预览提示词只写了特殊分块「{entry['label']}」，"
                        "没有写清它的形态：要写清方向／倾角／走向／弯曲程度／圆心位置"
                    )
        plan = plan_by_slide.get(page["id"]) or {}
        for image in ([] if page_type.get(page["id"]) in {"title", "toc"}
                      else plan.get("images") or []):
            target = asset_path(project, image.get("path") or "")
            if not target.is_file():
                continue
            with Image.open(target) as opened:
                aspect = opened.width / opened.height
            if prompt and not any(token in prompt for token in ratio_tokens(aspect)):
                errors.append(
                    f"{page['id']} 的整页预览提示词没有写明 {image['id']} 的图片位比例"
                    f"（约 {aspect:.2f}:1）：提示词要逐张写清图片位的精确比例，"
                    "预览里按该比例画占位块"
                )
        if stage == "2.2":
            errors += insertion_errors(project, page, plan_by_slide.get(page["id"]), record)
            if not str(page.get("review") or "").strip():
                errors.append(f"{page['id']} 原图插入后尚未登记逐页实际看图结论 review")
        if stage == "2.1" and page.get("localPlaceholderRepairs"):
            if record.get("output") != page.get("providerFile"):
                errors.append(f"{page['id']} 本地修框的原页来源与账本不一致")
            errors += local_frame_errors(project, page, plan_by_slide.get(page["id"]), concept=True)
        errors += placeholder_errors(
            project, page, plan_by_slide.get(page["id"]), job,
            page_type=page_type.get(page["id"])
        )
    errors += preview_prompt_errors(
        project, stage, job_ids={page["jobId"] for page in preview["pages"]}
    )
    # Palette diagnostics are reported by workflow completion, not error gates.
    if not design_spec.is_file():
        errors.append(f"缺少设计稿：{design_spec.relative_to(project).as_posix()}")
    return list(dict.fromkeys(errors))


def generation_evidence_errors(project, stage):
    """Require successful configured API calls for every registered preview page."""
    errors = ai_image_config_errors(project)
    if errors:
        return errors
    try:
        config = read_json(project / "00_intake/ai-image-config.json")
    except (OSError, ValueError, TypeError) as exc:
        return [f"AI 生图配置不可用：{exc}"]
    errors += generation_jobs_errors(project, stage, config)
    errors += generation_ledger_errors(project, stage, config)
    errors = list(dict.fromkeys(errors))
    if errors:
        return errors
    jobs_path, ledger_path, _ = _generation_paths(stage)
    by_id = {job["id"]: job for job in read_json(project / jobs_path)["jobs"]}
    ledgers = read_json(project / ledger_path)["jobs"]
    manifests = []
    if stage == "2.1":
        for option in STYLE_IDS:
            manifest = read_preview_pages(project, stage, option)
            if manifest:
                manifests.append(manifest)
    else:
        manifest = read_preview_pages(project, stage)
        if manifest:
            manifests.append(manifest)
    if not manifests:
        return errors + [
            f"阶段 {stage} 缺少整页预览清单，无法核对实际生图证据"
        ]
    seen = set()
    for manifest in manifests:
        for page in manifest.get("pages", []):
            identifier = page.get("jobId")
            seen.add(identifier)
            job = by_id.get(identifier)
            if job is None:
                errors.append(
                    f"{page.get('id', '未命名页面')} 的整页预览没有稳定生图任务：{identifier}"
                )
                continue
            if not (project / job["output"]).is_file():
                errors.append(
                    f"{page.get('id', '未命名页面')} 的整页预览输出已缺失：{job['output']}"
                )
            record = ledgers.get(identifier)
            if record is None or record.get("status") != "complete":
                errors.append(f"整页预览任务 {identifier} 尚未成功完成")
    # An edited preview consumes its prior generated image. Retaining that
    # source is required for the evidence chain; it is not an unused output.
    by_asset = {job.get('asset_id'): identifier for identifier, job in by_id.items()}
    pending = list(seen)
    while pending:
        current = by_id.get(pending.pop()) or {}
        source = (current.get('edit_source') or {}).get('assetId')
        parent = by_asset.get(source)
        if parent and parent not in seen:
            seen.add(parent)
            pending.append(parent)
    unused = sorted(set(by_id) - seen)
    if unused:
        errors.append(f"以下生图任务没有被任何整页预览使用：{unused}")
    return list(dict.fromkeys(errors))


def referenced_generation_files(project, stage, option=None):
    """Return the evidence files an approval record must bind for this stage."""
    errors = generation_evidence_errors(project, stage)
    if errors:
        return errors, []
    jobs_path, ledger_path, _ = _generation_paths(stage)
    ledger = read_json(project / ledger_path)["jobs"]
    manifests = []
    if stage == "2.1":
        manifest = read_preview_pages(project, stage, option)
    else:
        manifest = read_preview_pages(project, stage)
    if manifest:
        manifests.append(manifest)
    files = [jobs_path, ledger_path]
    for manifest in manifests:
        for page in manifest.get("pages", []):
            files.append(page["file"])
            if stage == "2.2":
                if page.get("providerFile"):
                    files.append(page["providerFile"])
                files.extend(item["path"] for item in page.get("originals", []))
            record = ledger.get(page["jobId"]) or {}
            if record.get("raw_path"):
                files.append(record["raw_path"])
    return [], sorted(set(files))


def speaker_script_errors(project):
    """Optional stage 4: per-page speaking notes plus a written script."""
    content = read_json(project / "02_design/content.json")
    if not content.get("include_speaker_script"):
        return ["用户已确认不需要演讲稿：阶段 4 应跳过，工作流在 3.3 结束"]
    errors = []
    script_path = project / "08_speaker-notes/speaker-script.md"
    notes_path = project / "08_speaker-notes/notes.json"
    if not script_path.is_file():
        errors.append("缺少演讲稿：08_speaker-notes/speaker-script.md")
    if not notes_path.is_file():
        errors.append("缺少逐页演讲备注：08_speaker-notes/notes.json")
    if errors:
        return errors
    try:
        notes = read_json(notes_path)
    except (OSError, ValueError, TypeError) as exc:
        return [f"逐页演讲备注不可读：{exc}"]
    errors += schema_errors(notes, "speaker-notes")
    if errors:
        return errors
    expected = [slide["id"] for slide in content["slides"]]
    if [page["id"] for page in notes["pages"]] != expected:
        errors.append("逐页演讲备注的页面编号或顺序与 content.json 不一致")
    for page in notes["pages"]:
        text = page["notes"].strip()
        if len(text) < 30:
            errors.append(f"{page['id']} 的演讲备注太短：每页要写清这一页怎么讲")
        if "待填写" in text:
            errors.append(f"{page['id']} 的演讲备注还留着占位文字")
    script = script_path.read_text(encoding="utf-8-sig")
    for slide_id in expected:
        if slide_id not in script:
            errors.append(f"演讲稿没有写到 {slide_id}")
    for slide in content["slides"]:
        if slide["title"] and slide["title"] not in script:
            errors.append(f"演讲稿没有覆盖标题「{slide['title']}」")
    return list(dict.fromkeys(errors))


def approval_errors(project, kind):
    locations = {
        "requirements": "00_intake/requirements-approval.json",
        "concept": "03_concepts/approval.json",
        "preview": "04_full-preview/approval.json",
    }
    location = locations[kind]
    try:
        approval = read_json(project / location)
        errors = schema_errors(approval, "approval")
        if errors:
            return errors
        if approval["kind"] != kind:
            return [f"批准类型错误：{location}"]
        if kind == "requirements":
            required = {"00_intake/project-brief.md", "01_inventory/materials.json"}
        elif kind == "concept":
            option = approval.get("option")
            if not option:
                return errors + ["方案批准必须记录选中的 option"]
            errors += preview_pages_errors(project, "2.1", option)
            errors += design_errors(project)
            evidence_errors, generation_files = referenced_generation_files(
                project, "2.1", option
            )
            errors += evidence_errors
            required = {
                "03_concepts/concept-review.md",
                "02_design/design-spec.md",
                "02_design/content.json",
                "02_design/claim-map.json",
                "02_design/generated-assets.json",
                "02_design/image-intent-plan.json",
                "03_concepts/generation-jobs.json",
                "03_concepts/generation-ledger.json",
                f"03_concepts/option-{option}/preview.json",
            }
            required.update(generation_files)
            previews = sorted(project.glob(f"03_concepts/option-{option}/*.png"))
            if not 1 <= len(previews) <= 3:
                errors.append("已选方案必须有 1 至 3 页整页预览 PNG")
            required.update(path.relative_to(project).as_posix() for path in previews)
        else:
            errors += preview_pages_errors(project, "2.2")
            evidence_errors, generation_files = referenced_generation_files(project, "2.2")
            errors += evidence_errors
            required = {
                "02_design/design-spec.md",
                "02_design/content.json",
                "02_design/generated-assets.json",
                "02_design/image-intent-plan.json",
                "02_design/image-plan.json",
                "04_full-preview/previews.json",
                "04_full-preview/generation-jobs.json",
                "04_full-preview/generation-ledger.json",
            }
            required.update(generation_files)
            previews = sorted(project.glob("04_full-preview/slides/*.png"))
            required.update(path.relative_to(project).as_posix() for path in previews)
        if not required.issubset(approval["files"]):
            errors.append(f"{kind} 批准记录没有绑定全部必需文件")
        return errors + check_hashes(project, approval["files"])
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return [f"缺少或无效的 {kind} 批准记录：{exc}"]


def material_errors(project):
    materials = read_json(project / "01_inventory/materials.json")
    errors = schema_errors(materials, "materials")
    if errors:
        return errors
    seen = set()
    for item in materials["materials"]:
        if item["id"] in seen:
            errors.append(f"重复材料编号：{item['id']}")
        seen.add(item["id"])
        errors.extend(check_hashes(project, {item["path"]: item["sha256"]}))
    return errors


def _image_aspect(project, intent_image, generated_by_id, materials_by_id):
    """Pixel aspect of a planned source image, or None when it is not available yet."""
    source = str(intent_image.get("sourceId") or "")
    candidate = None
    if source.startswith("GEN-"):
        asset = generated_by_id.get(source)
        if asset and asset.get("path"):
            candidate = project / asset["path"]
    else:
        material = materials_by_id.get(source)
        if material and material.get("path"):
            path = Path(material["path"])
            candidate = path if path.is_absolute() else project / path
    if candidate is None or not candidate.is_file():
        return None
    try:
        from PIL import Image

        with Image.open(candidate) as image:
            width, height = image.size
    except Exception:
        return None
    return (width / height) if height else None


def deck_style_errors(project):
    """Stage 2.2: the design spec must record the chosen style and palette."""
    errors = []
    spec_path = project / "02_design/design-spec.md"
    if not spec_path.is_file():
        return ["缺少设计稿：02_design/design-spec.md"]
    spec = spec_path.read_text(encoding="utf-8-sig")
    label = "- **选定风格与色彩：**"
    if label not in spec:
        errors.append(
            "设计稿缺少「- **选定风格与色彩：**」：阶段 2.2 要把用户选定的风格与配色补进设计稿"
        )
    else:
        line = spec[spec.index(label):].split("\n")[0]
        if (len(line.strip()) <= len(label) + 2
                or "阶段2.1用户选定后填写" in line):
            errors.append("设计稿的「选定风格与色彩」还空着：请在全篇视觉约定中写清选定风格与配色，逐页只写差异")
    approval = project / "03_concepts/approval.json"
    if not approval.is_file():
        errors.append("缺少方案批准记录：03_concepts/approval.json")
    elif not read_json(approval).get("option"):
        errors.append("方案批准记录缺少选定方案编号")
    return errors


def candidate_style_errors(
    assets, include_toc=False, include_thanks=False, require_tags=True
):
    """Stage 1.2: candidates must come in sets per design direction (a/b/c)."""
    errors = []
    by_style = {}
    for asset in assets:
        style = asset.get("styleId")
        if style not in STYLE_IDS:
            if require_tags:
                errors.append(
                    f"{asset.get('id', '未命名候选图')} 缺少 styleId："
                    "阶段 1.2 的候选图要按三种设计方向（a/b/c）成组登记"
                )
            continue
        by_style.setdefault(style, []).append(asset)
    if not require_tags and not by_style:
        return errors
    for style in STYLE_IDS:
        kinds = {asset.get("kind") for asset in by_style.get(style, [])}
        label = f"设计方向 {style}"
        if "hero-image" not in kinds:
            errors.append(f"{label} 缺少封面大图候选（kind: hero-image）")
        if "content-background" not in kinds:
            errors.append(
                f"{label} 缺少内容页背景底图候选（kind: content-background）"
            )
        if include_toc and "toc-image" not in kinds:
            errors.append(f"{label} 缺少目录页主图候选（kind: toc-image）")
        # 致谢页复用 content-background；历史 thanks-image 候选可保留但不强制。
    return errors


def content_plan_source_index_errors(text, materials):
    heading = re.search(r"^## 文案与材料原文索引\s*$", text, re.M)
    if not heading:
        return ["内容清单缺少《文案与材料原文索引》：先建立文案与材料原文对应关系，再进入设计稿"]
    section = re.split(r"^## ", text[heading.end():], maxsplit=1, flags=re.M)[0]
    columns = ("文案编号", "PPT候选文案", "材料ID", "原文定位", "原文摘录", "整理方式")
    header = None
    rows = []
    for line in section.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [cell.strip().replace(r"\|", "|")
                 for cell in re.split(r"(?<!\\)\|", line.strip().strip("|"))]
        if all(re.fullmatch(r":?-+:?", cell) for cell in cells):
            continue
        if header is None:
            if not all(column in cells for column in columns):
                return ["文案与材料原文索引缺少必要列：" + "、".join(columns)]
            header = cells
        else:
            rows.append(dict(zip(header, cells)))
    if not rows:
        return ["文案与材料原文索引没有文案记录"]
    known_materials = {material["id"] for material in materials}
    errors = []
    indexed = set()
    for row in rows:
        identifier = row.get("文案编号", "")
        if not re.fullmatch(r"CP-\d{3,}", identifier):
            errors.append("原文索引的文案编号须使用CP-###：" + identifier)
        indexed.add(identifier)
        for column in columns:
            value = row.get(column, "")
            if not value or "待填写" in value:
                errors.append(f"{identifier} 的原文索引未填写「{column}」")
        source = row.get("材料ID", "")
        if source == "结构文案":
            if row.get("整理方式") != "结构文案":
                errors.append(f"{identifier} 无材料原文时，整理方式须明确标为结构文案")
        else:
            for source_id in re.split(r"[\s,，、;；]+", source):
                if source_id and source_id not in known_materials and source_id != "用户说明":
                    errors.append(f"{identifier} 的原文索引引用未登记材料：{source_id}")
            for column in ("原文定位", "原文摘录"):
                if row.get(column) in {"无", "不适用", "—", "-"}:
                    errors.append(f"{identifier} 有材料来源但缺少有效「{column}」")
    narrative = text[:heading.start()] + text[heading.end() + len(section):]
    referenced = set(re.findall(r"(?<![A-Za-z0-9_-])CP-\d{3,}(?![A-Za-z0-9_-])", narrative))
    if not referenced:
        errors.append("内容清单正文须用CP-###关联候选文案与原文索引")
    for identifier in sorted(referenced - indexed):
        errors.append(f"正文文案 {identifier} 缺少原文索引")
    for identifier in sorted(indexed - referenced):
        errors.append(f"原文索引 {identifier} 未在候选文案正文中引用")
    return list(dict.fromkeys(errors))


def content_plan_errors(project):
    """Stage 1.2: selected copy and candidate images, written down in one document."""
    errors = []
    intent_path = project / "02_design/image-intent-plan.json"
    if not intent_path.is_file():
        return ["缺少图片意图：02_design/image-intent-plan.json（阶段 1.2 要选出入册的图片）"]
    intent = read_json(intent_path)
    errors += schema_errors(intent, "image-intent-plan")
    generated = read_json(project / "02_design/generated-assets.json")
    errors += schema_errors(generated, "generated-assets")
    plan = project / "02_design/content-plan.md"
    if not plan.is_file():
        errors.append(
            "缺少内容清单：02_design/content-plan.md"
            "（阶段 1.2 要把选出的文字与候选图片按叙述顺序写成一个 .md）"
        )
        return errors
    if errors:
        return errors
    text = plan.read_text(encoding="utf-8-sig")
    errors += content_plan_source_index_errors(
        text, read_json(project / "01_inventory/materials.json")["materials"]
    )
    if "##" not in text:
        errors.append(
            "内容清单要用 Markdown 分级：同级文字写在同一层，避免平行结构"
        )
    assets = generated.get("assets", [])
    errors += candidate_style_errors(assets)
    for asset in assets:
        identifier = asset["id"]
        path = project / asset["path"]
        if not path.is_file():
            errors.append(f"{identifier} 的候选图片不存在：{asset['path']}")
            continue
        errors += check_hashes(project, {asset["path"]: asset["sha256"]})
        if not str(asset.get("intendedUse") or "").strip():
            errors.append(f"{identifier} 缺少用途说明：每张候选图片都要写清它是什么")
        try:
            from PIL import Image

            with Image.open(path) as image:
                width, height = image.size
        except Exception as exc:  # noqa: BLE001 - 任何解码失败都算不合格
            errors.append(f"{identifier} 不是可读的图片：{exc}")
            continue
        if height and width / height < 1.2:
            errors.append(
                f"{identifier} 不是横版（{width}×{height}）：候选图片统一用横版"
            )
    for asset in assets:
        if asset["id"] not in text:
            errors.append(f"内容清单没有写到候选图片 {asset['id']}")
    for slide in intent["slides"]:
        for image in slide["images"]:
            if image["id"] not in text:
                errors.append(f"内容清单没有写到图片 {image['id']}（{slide['id']}）")
    return list(dict.fromkeys(errors))


def ratio_tokens(aspect):
    """一个图片比例在提示词里可以怎么写（小数、"宽:高"、常见比例）。"""
    tokens = {f"{aspect:.2f}", f"{aspect:.1f}", f"{aspect:.2f}:1", f"{aspect:.1f}:1"}
    for width, height in (
        (16, 9), (4, 3), (3, 2), (5, 4), (21, 9), (1, 1),
        (3, 1), (2, 1), (4, 1), (9, 16), (3, 4), (2, 3),
    ):
        if abs(width / height - aspect) / aspect <= 0.03:
            tokens |= {f"{width}:{height}", f"{width}：{height}", f"{width}/{height}"}
    return tokens


def _nearest_line(candidates, target, tolerance):
    """离目标位置最近且在容差内的候选线；没有就返回 None。"""
    close = [value for value in candidates if abs(value - target) <= tolerance]
    return min(close, key=lambda value: abs(value - target)) if close else None


def stop_point_label(stage):
    return f"{stage}（{STOP_POINTS[stage]}）" if stage in STOP_POINTS else stage


def next_stop_point(project_stage):
    """The first designated stop point at or after a stage."""
    if project_stage in STAGES:
        for stage in STAGES[STAGES.index(project_stage):]:
            if stage in STOP_POINTS:
                return stage
    return None


def stop_point_status(project):
    """Report whether the pipeline may stop here.

    Only the designated stop points (and the final delivery) may end an agent
    turn: everywhere else the workflow has to keep running.
    """
    state = read_json(project / "workflow-state.json")
    stages = state.get("stages", {}) if isinstance(state, dict) else {}
    waiting = [
        stage
        for stage in STAGES[1:]
        if (stages.get(stage) or {}).get("status") == "awaiting_user"
    ]
    legal = "、".join(stop_point_label(stage) for stage in STOP_POINT_ORDER)
    off_point = [stage for stage in waiting if stage not in STOP_POINTS]
    if off_point:
        stage = off_point[0]
        return {
            "stage": stage,
            "status": "awaiting_user",
            "stopPoint": False,
            "canStop": False,
            "reason": (
                f"阶段 {stage} 不是停机点：停机点只有 {legal}；"
                "请继续执行到下一个停机点，不要在这里结束任务进程"
            ),
        }
    if waiting:
        stage = waiting[0]
        if stage == "2.2":
            errors = preview_pages_errors(project, "2.2")
            if errors:
                return {"stage": stage, "status": "awaiting_user", "stopPoint": True,
                        "canStop": False, "reason": "完整预览必须先插入原图并逐页检查：" + "；".join(errors)}
        return {
            "stage": stage,
            "status": "awaiting_user",
            "stopPoint": True,
            "canStop": True,
            "reason": (
                f"阶段 {stop_point_label(stage)} 是停机点："
                "把结论或方案交给用户，等确认后再继续"
            ),
        }
    pending = [
        stage for stage in STAGES[1:] if (stages.get(stage) or {}).get("status") != "complete"
    ]
    if not pending:
        return {
            "stage": STAGES[-1],
            "status": "complete",
            "stopPoint": False,
            "canStop": True,
            "terminal": True,
            "reason": "全部阶段已完成：任务已交付，可以结束",
        }
    stage = pending[0]
    target = next_stop_point(stage)
    hint = (
        f"下一个停机点是阶段 {stop_point_label(target)}"
        if target
        else "继续推进到最后交付"
    )
    return {
        "stage": stage,
        "status": (stages.get(stage) or {}).get("status", "not_started"),
        "stopPoint": False,
        "canStop": False,
        "reason": f"阶段 {stage} 尚未完成：{hint}，中途不得结束任务进程",
    }


def stop_point_errors(project, stage):
    """A stop-point stage may only be completed after it waited for the user."""
    if stage not in STOP_POINTS:
        return []
    state = read_json(project / "workflow-state.json")
    status = (state.get("stages", {}).get(stage) or {}).get("status")
    if status == "awaiting_user":
        return []
    return [
        f"阶段 {stop_point_label(stage)} 是停机点：必须先停在这里等用户确认"
        f"（每个停机点都要先运行 `await <阶段>`：`await 1.1`、`await 1.3`、`await 2.1`、`await 2.2`），"
        "再执行 complete；停机点之外不允许中断任务进程"
    ]


def gate_errors(
    project,
    through="3.2",
    verify_materials=True,
    verify_previews=True,
):
    errors = []
    state = read_json(project / "workflow-state.json")
    errors += schema_errors(state, "state")
    if errors:
        return errors
    for stage in STAGES[1:STAGES.index(through) + 1]:
        record = state["stages"].get(stage, {})
        if not isinstance(record, dict) or record.get("status") != "complete":
            errors.append(f"阶段 {stage} 未完成")
            continue
        current = collect(project, stage)
        if current != record.get("files"):
            errors.append(f"阶段 {stage} 产物已变化或未绑定版本，需要重新完成")
        if verify_previews:
            errors += stage_preview_errors(project, stage)
    if STAGES.index(through) >= STAGES.index("1.1"):
        errors += ai_image_config_errors(project)
        errors += approval_errors(project, "requirements")
        if verify_materials:
            errors += material_errors(project)
    if STAGES.index(through) >= STAGES.index("2.1") and verify_previews:
        errors += generation_evidence_errors(project, "2.1")
        errors += approval_errors(project, "concept")
    if STAGES.index(through) >= STAGES.index("2.2") and verify_previews:
        errors += generation_evidence_errors(project, "2.2")
        errors += approval_errors(project, "preview")
    return list(dict.fromkeys(errors))


def layout_adjustment_errors(spec):
    """Layout polish is authorized by the workflow; retain its reason and baseline."""
    errors = []
    adjusted = [element for slide in spec.get("slides", [])
                for element in slide.get("elements", []) if "layoutAdjustment" in element]
    if adjusted and not str(spec.get("meta", {}).get("layoutAdjustmentAuthorization", "")).strip():
        errors.append("成品位置调整缺少 meta.layoutAdjustmentAuthorization：记录用户原话或本工作流的美化授权，不必重复询问")
    for element in adjusted:
        record = element.get("layoutAdjustment")
        before = record.get("from", {}) if isinstance(record, dict) else {}
        if not isinstance(before, dict) or not all(
            isinstance(before.get(key), (int, float))
            and not isinstance(before[key], bool) and math.isfinite(before[key])
            for key in ("x", "y")
        ):
            errors.append(f"{element['id']} 的 layoutAdjustment.from 必须记录调整前的有限英寸坐标 x／y")
        if not isinstance(record, dict) or not str(record.get("reason", "")).strip():
            errors.append(f"{element['id']} 的 layoutAdjustment 缺少美化原因")
    for slide in spec.get("slides", []):
        for element in slide.get("elements", []):
            if element.get("boundaryMask") and element.get("type") != "image":
                errors.append(f"{element['id']} 的 boundaryMask 只用于图片；文本框裁切框体并保留独立原生文字")
            if element.get("boundaryMask"):
                try:
                    boundary_mask(element["boundaryMask"], (8, 8))
                except (ValueError, KeyError, TypeError, AttributeError) as exc:
                    errors.append(f"{element['id']} 的 boundaryMask 无效：{exc}")
    return errors


def image_plan_errors(project, spec, require_pages=True):
    errors = []
    image_plan = read_json(project / "02_design/image-plan.json")
    errors += schema_errors(image_plan, "image-plan")
    if errors:
        return errors
    errors += image_plan_geometry_errors(image_plan)
    if not image_plan["slides"]:
        actual_images = [
            element["id"]
            for slide in spec.get("slides", [])
            for element in slide.get("elements", [])
            if element.get("type") == "image" and is_planned_image(element)
        ]
        if actual_images:
            errors.append("deck-spec 已包含图片，但 image-plan 仍为空")
        if require_pages:
            errors.append("image-plan 必须覆盖全部定稿页面")
        return errors
    content_ids = [slide["id"] for slide in read_json(project / "02_design/content.json")["slides"]]
    plan_ids = [slide["id"] for slide in image_plan["slides"]]
    spec_ids = [slide["id"] for slide in spec["slides"]]
    if plan_ids != content_ids:
        errors.append("image-plan 页面与 content.json 不一致")
    if plan_ids != spec_ids:
        errors.append("image-plan 页面与 deck-spec.json 不一致")
    canvas_width, canvas_height = canvas(spec)
    spec_slides = {slide["id"]: slide for slide in spec["slides"]}
    for slide in image_plan["slides"]:
        elements = {element["id"]: element for element in spec_slides.get(slide["id"], {}).get("elements", [])}
        planned_ids = {image["id"] for image in slide["images"]}
        actual_ids = {
            element["id"]
            for element in elements.values()
            if element["type"] == "image" and is_planned_image(element)
        }
        if planned_ids != actual_ids:
            missing = sorted(planned_ids - actual_ids)
            extra = sorted(actual_ids - planned_ids)
            if missing:
                errors.append(f"{slide['id']} 缺少图片计划元素：{missing}")
            if extra:
                errors.append(f"{slide['id']} 存在未列入 image-plan 的图片元素：{extra}")
            continue
        for image in slide["images"]:
            element = elements[image["id"]]
            expected_box = normalized_box_to_inches(image["box"], canvas_width, canvas_height)
            adjustment = element.get("layoutAdjustment") or {}
            before = adjustment.get("from", {}) if isinstance(adjustment, dict) else {}
            baseline_matches = isinstance(before, dict) and all(
                isinstance(before.get(key), (int, float))
                and not isinstance(before[key], bool)
                and math.isclose(before[key], expected_box[key], abs_tol=0.01)
                for key in ("x", "y")
            )
            position_adjusted = bool(
                baseline_matches and isinstance(adjustment, dict)
                and str(adjustment.get("reason", "")).strip()
                and str(spec.get("meta", {}).get("layoutAdjustmentAuthorization", "")).strip()
            )
            if adjustment and not baseline_matches:
                errors.append(f"{image['id']} 的位置调整起点与 image-plan 不一致：必须保留已批准计划的原始英寸坐标")
            for key in ("x", "y", "w", "h"):
                if key in {"x", "y"} and position_adjusted:
                    continue
                if not math.isclose(element[key], expected_box[key], abs_tol=0.01):
                    errors.append(
                        f"{image['id']} 的 {key} 与 image-plan 归一化位置不一致："
                        f"deck-spec={element[key]:.4f} in, image-plan={expected_box[key]:.4f} in"
                    )
            if element.get("sourceId") != image["sourceId"]:
                errors.append(f"{image['id']} 的 sourceId 与 image-plan 不一致")
            if element.get("fit", "contain") != image["fit"]:
                errors.append(f"{image['id']} 的 fit 与 image-plan 不一致")
            z_adjusted = position_adjusted and before.get("z") == image["z"]
            if element.get("z", 0) != image["z"] and not z_adjusted:
                errors.append(f"{image['id']} 的 z 与 image-plan 不一致")
            mask_adjusted = (
                position_adjusted and "boundaryMask" in before
                and before["boundaryMask"] == image.get("boundaryMask")
            )
            if element.get("boundaryMask") != image.get("boundaryMask") and not mask_adjusted:
                errors.append(f"{image['id']} 的 boundaryMask 与 image-plan 不一致：成品边缘裁切须记录原始轮廓与授权")
            if element.get("altText") != image["altText"]:
                errors.append(f"{image['id']} 的 altText 与 image-plan 不一致")
            if image.get("focal") and element.get("focal") != image["focal"]:
                errors.append(f"{image['id']} 的 focal 与 image-plan 不一致")
            if image.get("crop") and element.get("crop") != image["crop"]:
                errors.append(f"{image['id']} 的 crop 与 image-plan 不一致")
            if image.get("path") and element.get("path") != image["path"]:
                errors.append(f"{image['id']} 的 path 与 image-plan 不一致")
    return errors


def canvas(spec):
    meta = spec["meta"]
    if meta["layout"] == "CUSTOM":
        return meta["width"], meta["height"]
    return (10.0, 7.5) if meta["layout"] == "LAYOUT_4X3" else (13.333333, 7.5)


def is_planned_image(element):
    return element.get("origin", "planned") == "planned"


def svg_errors(text):
    try:
        root = ET.fromstring(text)
        box = [float(n) for n in root.attrib.get("viewBox", "").replace(",", " ").split()]
        if root.tag.split("}")[-1] != "svg" or len(box) != 4 or box[2] <= 0 or box[3] <= 0:
            return ["SVG 必须有有效的 viewBox"]
        for element in root.iter():
            tag = element.tag.split("}")[-1]
            if tag in {"script", "foreignObject", "image"}:
                return ["SVG 不允许脚本、foreignObject 或嵌入位图"]
            for key, value in element.attrib.items():
                lowered = value.strip().lower()
                if any(
                    token in lowered
                    for token in ("javascript:", "data:", "http://", "https://")
                ):
                    return ["SVG 不允许外部资源或嵌入位图"]
                if key.split("}")[-1] == "href" and not value.startswith("#"):
                    return ["SVG 不允许外部资源或嵌入位图"]
        return []
    except (ValueError, ET.ParseError):
        return ["SVG XML 或 viewBox 无效"]


def text_fit_errors(label, element, box_px, page_type=None, note=""):
    """文字要放得进文本框；实际字号在本地设计/重建规格中核对，不写入生图提示词。"""
    errors = []
    try:
        size, metrics = fit_text_size(element, box_px)
    except (OSError, ValueError, KeyError, TypeError):
        return errors
    if metrics.get("bitmap_default"):
        return errors
    if not fits(metrics):
        errors.append(
            f"{label} 的文字放不进文本框{note}："
            f"估算 {metrics['line_count']} 行、最宽 {metrics['max_line_width']:.0f}px "
            f"超过框宽 {box_px[2]:.0f}px／框高 {box_px[3]:.0f}px；"
            "放大文本框或减少文字"
        )
    return errors


def boxed_text_shape(slide, element):
    """文字是否被某个色块完全套住（该色块就是它的文本框）。"""
    text_area = max(1e-6, element["w"] * element["h"])
    for other in slide["elements"]:
        if other is element or other.get("type") != "shape":
            continue
        if other.get("shape") == "line":
            continue
        overlap_w = max(
            0.0,
            min(element["x"] + element["w"], other["x"] + other["w"])
            - max(element["x"], other["x"]),
        )
        overlap_h = max(
            0.0,
            min(element["y"] + element["h"], other["y"] + other["h"])
            - max(element["y"], other["y"]),
        )
        if overlap_w * overlap_h / text_area >= TEXT_BOX_COVER:
            return other
    return None


def spec_text_errors(slide, element, label, page_type=None):
    """Check text fit and font floors; semantic alignment is a visual review decision."""
    errors = []
    box_px = (
        inch_to_px(element["x"]),
        inch_to_px(element["y"]),
        inch_to_px(element["w"]),
        inch_to_px(element["h"]),
    )
    measure = {**element}
    if element.get("fontSize"):
        measure["fontSizePt"] = element["fontSize"]
        measure["fontSize"] = pt_to_px(element["fontSize"])
    errors += text_fit_errors(label, measure, box_px, page_type)
    return errors


def spec_errors(project, spec, release=False):
    errors = schema_errors(spec, "deck")
    if errors:
        return errors
    width, height = canvas(spec)
    page_type = {}
    try:
        page_type = {
            slide["id"]: slide.get("page_type")
            for slide in read_json(project / "02_design/content.json")["slides"]
        }
    except (OSError, ValueError, TypeError, KeyError):
        page_type = {}
    seen = set()
    all_ids = set()
    for slide in spec["slides"]:
        if slide["id"] in seen:
            errors.append(f"重复页面编号：{slide['id']}")
        seen.add(slide["id"])
        for element in slide["elements"]:
            label = f"{slide['id']}/{element['id']}"
            if element["id"] in all_ids:
                errors.append(f"重复元素编号：{label}")
            all_ids.add(element["id"])
            x, y, w, h = [element[k] for k in ("x", "y", "w", "h")]
            if not all(math.isfinite(v) for v in (x, y, w, h)):
                errors.append(f"非有限坐标：{label}")
            bleed = set(element.get("bleed", []))
            overflow_sides = set()
            if x < -0.01:
                overflow_sides.add("left")
            if y < -0.01:
                overflow_sides.add("top")
            if x + w > width + 0.01:
                overflow_sides.add("right")
            if y + h > height + 0.01:
                overflow_sides.add("bottom")
            if overflow_sides and not element.get("allowOverflow") and not overflow_sides.issubset(bleed):
                errors.append(f"元素越界：{label}；有意出血须在 bleed 中列出对应边")
            if (w == 0 or h == 0) and not (element["type"] == "shape" and element["shape"] == "line"):
                errors.append(f"零尺寸元素：{label}")
            if element["type"] in {"image", "svg"}:
                path = asset_path(project, element["path"]) if element.get("path") else None
                if path and not path.is_file():
                    errors.append(f"素材缺失：{label}: {path}")
                elif element["type"] == "svg":
                    text = element.get("svg") or path.read_text(encoding="utf-8-sig")
                    errors.extend(f"{label}: {message}" for message in svg_errors(text))
            if element["type"] == "table" and len({len(row) for row in element["rows"]}) != 1:
                errors.append(f"表格行列数不一致：{label}")
            if element["type"] == "chart":
                for series in element["data"]:
                    if len(series["labels"]) != len(series["values"]):
                        errors.append(f"图表标签与数值数量不一致：{label}")
            if element["type"] == "text":
                errors.extend(
                    spec_text_errors(
                        slide, element, label, page_type.get(slide["id"])
                    )
                )
    errors += layout_adjustment_errors(spec)
    errors += image_plan_errors(project, spec, require_pages=release)
    if release:
        if not math.isclose(width / height, 16 / 9, abs_tol=1e-6):
            errors.append("正式 PPTX 画布必须为 16:9，与预览保持一致")
        errors += content_errors(project, spec)
        errors += ai_major_image_errors(project, spec)
        errors += rebuilt_asset_errors(project, spec)
    return errors


def content_errors(project, spec):
    content = read_json(project / "02_design/content.json")
    errors = schema_errors(content, "content")
    if errors:
        return errors
    if [s["id"] for s in content["slides"]] != [s["id"] for s in spec["slides"]]:
        return ["构建页面编号或顺序与定稿 content.json 不一致"]
    materials = {m["id"] for m in read_json(project / "01_inventory/materials.json")["materials"]}
    sections = content.get("sections") or []
    section_titles = {section["title"] for section in sections}
    progress = content.get("progress_bar") or {}
    excluded = set(progress.get("exclude_page_types") or [])
    for source, slide in zip(content["slides"], spec["slides"]):
        expected = {e["id"]: e["text"] for e in source["texts"]}
        actual = {}
        for element in slide["elements"]:
            if element["type"] != "text":
                continue
            if element.get("origin") == "progress":
                # 顶部进度条的标题文本：不属于页面文案，文字必须逐字取自 sections
                if element["text"].strip() not in section_titles:
                    errors.append(
                        f"{slide['id']}/{element['id']} 是进度条标题文本，"
                        "文字必须逐字取自 content.json 的 sections"
                    )
                if progress.get("enabled") is not True:
                    errors.append(
                        f"{slide['id']}/{element['id']} 是进度条文本，但 progress_bar 未启用"
                    )
                elif source["page_type"] in excluded:
                    errors.append(
                        f"{slide['id']}/{element['id']} 是进度条文本，"
                        f"但 {source['page_type']} 页面按配置不应出现进度条"
                    )
                continue
            actual[element["id"]] = element["text"]
        if len(expected) != len(source["texts"]) or expected != actual:
            errors.append(f"{slide['id']} 的文本编号或准确文案与定稿不一致")
        if not set(source["materials"]).issubset(materials):
            errors.append(f"{slide['id']} 引用了未登记的材料")
    return errors


def spec_warnings(spec):
    warnings = []
    for slide in spec["slides"]:
        for element in slide["elements"]:
            if element.get("allowOverflow"):
                warnings.append(f"{slide['id']}/{element['id']} 仍使用旧版 allowOverflow；请迁移为 bleed 逐边声明")
    return warnings


def page_versions(project, spec):
    content_hash = digest(project / "02_design/content.json")
    image_plan_hash = digest(project / "02_design/image-plan.json")
    preview_hashes = {
        path.stem: digest(path)
        for path in sorted(project.glob("04_full-preview/slides/*.png"))
    }
    result = {}
    for slide in spec["slides"]:
        images = [element for element in slide["elements"] if element["type"] == "image"]
        result[slide["id"]] = {
            "content_sha256": content_hash,
            "image_plan_sha256": image_plan_hash,
            "preview_sha256": preview_hashes.get(slide["id"]),
            "asset_ids": [element["id"] for element in images],
        }
    return result


def ai_major_image_errors(project, spec):
    """Generated candidates need not appear; adopted assets use plan/inventory gates.

    Image-plan identity and rebuilt-element checks still reject missing adopted
    objects. Presence in the candidate registry alone creates no display duty.
    """
    return []


def rebuilt_asset_errors(project, spec):
    manifest = read_json(project / "05_reconstruction/assets.json")
    if not isinstance(manifest, dict) or not isinstance(manifest.get("assets"), list):
        return ["无效的重建素材清单"]
    errors = []
    indexed = {}
    for item in manifest["assets"]:
        if not isinstance(item, dict) or not all(k in item for k in ("path", "sha256", "sourceId")):
            errors.append("素材清单缺少 path、sha256 或 sourceId")
            continue
        indexed[str(asset_path(project, item["path"]).resolve())] = item
        errors += check_hashes(project, {item["path"]: item["sha256"]})
    originals = {m["id"]: m for m in read_json(project / "01_inventory/materials.json")["materials"]}
    for slide in spec["slides"]:
        for element in slide["elements"]:
            if element["type"] not in {"image", "svg"} or "path" not in element:
                continue
            source = element.get("sourceId")
            path = asset_path(project, element["path"])
            if not source:
                errors.append(f"{element['id']} 缺少 sourceId；生成素材使用 GEN-，重建素材使用 RECON-")
            elif source in originals:
                if digest(path) != originals[source]["sha256"]:
                    errors.append(f"{element['id']} 不是登记原图；请让构建器负责裁剪，不替换证据原件")
            elif source.startswith(("GEN-", "RECON-")):
                item = indexed.get(str(path.resolve()))
                if not item or item["sourceId"] != source:
                    errors.append(f"{element['id']} 生成或重建素材未登记")
            else:
                errors.append(f"{element['id']} 来源编号无效：{source}")
    return errors
