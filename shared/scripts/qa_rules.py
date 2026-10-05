"""Central preview rules: thresholds, element roles and text-role floors.

Shared by the preview checks and the tests so the numbers only live
in one place.
"""

from __future__ import annotations

RULES_VERSION = 12

CANVAS = (1920, 1080)

# --- content overlap (only decorative elements may overlap) -----------------
CONTENT_OVERLAP_ERROR = 0.02
CONTENT_OVERLAP_WARN = 0.005
CONTENT_GAP_WARN_PX = 8
COVERED_RATIO = 0.30
COVERED_OPACITY = 0.35

# --- text size floors, in preview pixels (delivery points = px / 2) ---------
TEXT_ROLE_FLOORS = {
    "title": 56,
    "subtitle": 40,
    "section": 40,
    "body": 36,
    "caption": 28,
    "label": 24,
    "source": 22,
    "page-number": 20,
}
DEFAULT_TEXT_ROLE = "body"
# 单段文字不要过长：超过上限就分点、拆成多个文本框。
TEXT_RUN_WARN_CHARS = 110
TEXT_RUN_MAX_CHARS = 180
TEXT_RUN_WARN_LINES = 7
TEXT_RUN_MAX_LINES = 10

# Title and TOC pages must read from the back of the room: higher floors apply.
TITLE_PAGE_TITLE_MIN = 72
TITLE_PAGE_SUBTITLE_MIN = 48
TOC_HEADING_MIN = 72
TOC_ENTRY_MIN = 52
TEXT_ROLE_TOKENS = (
    ("SUBTITLE", "subtitle"),
    ("KICKER", "label"),
    ("TOCITEM", "section"),
    ("TOC", "section"),
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
)

# --- blank space ------------------------------------------------------------
BLANK_REGION_RATIO = 0.28
BLANK_CELL_LIMIT = 4
LOW_DENSITY_INK = 0.06
LOW_DENSITY_ELEMENTS = 3

# --- text support -----------------------------------------------------------
SUPPORT_COVER_RATIO = 0.70
SUPPORT_NEIGHBOUR_PX = 12
SUPPORT_AREA_MIN = 0.02
SUPPORT_AREA_MAX = 1.20

# --- text box definition, inner decoration and holding lines ----------------
TEXT_BOX_COVER = 0.70
# 框内装饰可省略；仅在采用时检查位置、颜色与同级一致性。
TEXTBOX_INNER_MIN = 0
TEXTBOX_INNER_AREA_MAX = 0.45
TEXTBOX_INNER_EDGE_GAP = 2
LINE_HOLD_GAP_PX = 16
LINE_HOLD_MIN_LENGTH = 0.35
LINE_OVERLAP_TOLERANCE = 2
LINE_DIRECTION_TOLERANCE = 35.0
LINE_CLUTTER_WARN = 7
PROGRESS_TEXT_CLEARANCE = 6
PROGRESS_HEIGHT_MIN = 0.045
PROGRESS_HEIGHT_WARN = 0.05
COVER_HERO_FILL = 0.30
COVER_HERO_EDGE = 0.94
COVER_HERO_HEIGHT = 0.94
COVER_HERO_LEFT_ZONE = 0.50
LINE_HOLD_THICKNESS_MIN = 3
LINE_HOLD_THICKNESS_WARN = 5
INNER_ALLOWED_SHAPES = (
    "ring",
    "dots",
    "circle",
    "ellipse",
    "hexagon",
    "sparkle",
    "arrow-right",
    "arrow-left",
    "arrow-up",
    "arrow-down",
)
INNER_ALLOWED_DIAGONAL = ("lines", "split-block")
CONCEPT_VARIETY_LAYOUTS = ("layout_id", "textRoleSizes", "decorationKinds")
TOC_NUMBER_ZONE = 0.06
CONCEPT_DECOR_OVERLAP = 0.70
TOC_NUMBER_SHAPES = ("ring", "circle", "ellipse", "hexagon", "sparkle", "capsule", "diamond")
BLANK_REGION_RATIO_CONTENT = 0.18
PAGE_FILL_WIDTH = 0.72
PAGE_FILL_HEIGHT = 0.62
PAGE_FILL_AREA = 0.45
HERO_STYLE = "realistic-3d"
BACKGROUND_CENTER_RATIO = 0.5
BACKGROUND_CENTER_BUSY = 0.55
BACKGROUND_DETAIL_FLOOR = 0.10
RING_ASPECT_TOLERANCE = 0.06
RING_STROKE_MIN = 6
# 圆环线宽 ≈ 内径的一半：stroke / inner_radius 落在 [MIN, MAX] 内
RING_STROKE_RATIO = 0.5
RING_STROKE_RATIO_MIN = 0.35
RING_STROKE_RATIO_MAX = 0.75
LINE_HOLD_ANGLE_TOLERANCE = 2.0
# 清单声明的占位框与登记原件的宽高比允许偏差；预览实际框位由逐页看图确认
PHOTO_FRAME_ASPECT_TOLERANCE = 0.12
# 同风格：整页预览与所给 AI 大图的主色距离上限（0–441，越小越接近）
SAME_STYLE_PALETTE_TOLERANCE = 96
TEXTBOX_DECOR_REPEAT_WARN = 3
# 框内小元素要贴着文本框边缘，并裁掉出格的部分
TEXTBOX_INNER_EDGE_BAND = 24
# 文本框大小要与框内文字匹配：文字墨量占比低于下限说明框留了大量空白
TEXTBOX_FILL_MIN = 0.18
# 小元素要么完全落在框内（或裁切到框内），要么调低透明度压在框上当叠层
# 占位块框与计划框的归一化偏差上限
PLACEHOLDER_BOX_TOLERANCE = 0.02
TEXTBOX_OVERLAY_OPACITY = 0.6
# 椭圆／圆／气泡只能承载短文字，不能当长文字的文本框
ROUND_TEXTBOX_SHAPES = ("ellipse", "circle", "bubble")
TEXTBOX_ROUND_MAX_CHARS = 24
TEXTBOX_ROUND_MAX_LINES = 2
# 进度条底框要占满上边缘（允许 2px 误差）
PROGRESS_CONTAINER_TOP_TOLERANCE = 2
# 羽化只能吃边缘背景，不能侵入主体：主体区平均不透明度下限
FEATHER_SUBJECT_ALPHA_WARN = 0.95
FEATHER_SUBJECT_ALPHA_MIN = 0.88
FEATHER_FOCAL_BOX = 0.24
# 分区不要用一条长线：超过画布这个比例的长线按“用线分区”提示
DIVIDER_LINE_RATIO = 0.55
# 框内小元素要与文本框同一色系（色相差上限，度）
TEXTBOX_DECOR_HUE_TOLERANCE = 45
TOC_ASSET_MIN_AREA = 0.10
ORPHAN_DECOR_AREA_MAX = 0.03
ORPHAN_DECOR_GAP_PX = 40
ORPHAN_DECOR_SHAPES = (
    "ring",
    "dots",
    "sparkle",
    "lines",
    "arc",
    "line",
    "ellipse",
    "circle",
    "hexagon",
    "diamond",
    "triangle",
)
TEXT_ROTATION_LIMIT = 60
HERO_CROP_MIN = 0.55
ILLUSTRATION_HINT_MIN = 1
EDGE_MODES = ("none", "cutout", "feather")

# --- decorative vocabulary --------------------------------------------------
PLAIN_SHAPES = ("rectangle", "rounded-rectangle")
# 线阵 lines 与线条 line 同为词汇元素：文本框内装饰、页级装饰统计都要认它。
DECOR_VOCABULARY = ("line", "lines", "arc", "ring", "dots", "split-block")
DECOR_SHAPE_KINDS = (
    "line",
    "lines",
    "arc",
    "ring",
    "dots",
    "sparkle",
    "split-block",
    "ellipse",
    "circle",
    "capsule",
    "bubble",
    "triangle",
    "parallelogram",
    "trapezoid",
    "right-pentagon",
    "hexagon",
    "chevron",
    "v-shape",
    "diamond",
    "pentagon",
    "custom-polygon",
    "arrow-right",
    "arrow-left",
    "arrow-up",
    "arrow-down",
)
# 预览装饰词汇 -> PptxGenJS 预设名。阶段 3.1 记录映射、阶段 3.3 只能写右列名称，
# 写预览侧的名字会让构建器报 Unknown shape。
# 文本框形状：同级并列的文本框必须落在同一族，整页也不能全是尖角矩形。
TEXTBOX_SHAPE_FAMILIES = {
    "rectangle": "rectangle",
    "rounded-rectangle": "rounded",
    "capsule": "capsule",
    "bubble": "round",
    "ellipse": "round",
    "circle": "round",
    "hexagon": "hexagon",
    "trapezoid": "trapezoid",
    "pentagon": "pentagon",
    "right-pentagon": "pentagon",
    "diamond": "diamond",
    "triangle": "triangle",
    "parallelogram": "parallelogram",
    "chevron": "chevron",
    "v-shape": "chevron",
    "split-block": "split-block",
    "custom-polygon": "custom-polygon",
}
TEXTBOX_PLAIN_FAMILIES = ("rectangle", "rounded")

PREVIEW_TO_NATIVE_SHAPES = {
    "rectangle": ("rect",),
    "rounded-rectangle": ("roundRect",),
    "capsule": ("roundRect",),
    "bubble": ("ellipse", "cloud"),
    "ellipse": ("ellipse",),
    "circle": ("ellipse",),
    "line": ("line",),
    "lines": ("line",),
    "ring": ("donut", "ellipse"),
    "arc": ("arc",),
    "dots": ("ellipse",),
    "sparkle": ("star4",),
    "split-block": ("rect",),
    "right-pentagon": ("homePlate",),  # 构建规格里用 homePlate + rotate: 90，锐角朝右
    "triangle": ("triangle",),
    "parallelogram": ("parallelogram",),
    "trapezoid": ("trapezoid",),
    "hexagon": ("hexagon",),
    "chevron": ("chevron",),
    "arrow-right": ("rightArrow",),
    "arrow-left": ("leftArrow",),
    "arrow-up": ("upArrow",),
    "arrow-down": ("downArrow",),
    "pentagon": ("pentagon",),
    "diamond": ("diamond",),
    "v-shape": ("chevron",),
    "custom-polygon": ("rect", "triangle", "trapezoid", "parallelogram", "pentagon"),
}
PAGE_DECOR_MIN = 2
PAGE_DECOR_MIN_TITLE = 3
PAGE_DECOR_VOCAB_MIN = 1
PAGE_DECOR_VOCAB_MIN_TITLE = 2
TEXT_DECOR_INTERSECT = 0.03

# --- aesthetics and typography ----------------------------------------------
HIERARCHY_MIN = 1.30
HIERARCHY_MAX = 3.20
INFO_VISUAL_TEXTS = 3
ALIGN_GUIDE_MIN = 3
ALIGN_TOLERANCE_PX = 2
ALIGN_NEAR_MISS_MIN = 4
ALIGN_NEAR_MISS_MAX = 10
ALIGN_NEAR_MISS_COUNT = 3
GAP_VARIATION_MAX = 0.40
COLOR_MONOTONE_SHARE = 0.93
COLOR_CHROMA_MIN = 0.18
TONE_SATURATION_MAX = 0.90
TONE_VALUE_MAX = 0.95
TONE_AREA_MIN = 0.05
AESTHETIC_WARNING_LIMIT = 3

# --- text fitting -----------------------------------------------------------
OVERFLOW_TOLERANCE = 1.005
AUTOFIT_MIN_SCALE = 0.75

# --- misc quality gates -----------------------------------------------------
CONTRAST_FLOOR = 3.0
CONTRAST_TARGET = 4.5
HERO_RATIO = 0.20
ASSET_LIMIT = 6
ASSET_WARN = 4
TINY_ASSET = 0.03
SHAPE_WARN = 8
BACKGROUND_SPREAD_MAX = 0.35
BACKGROUND_SPREAD_WARN = 0.22
BACKGROUND_OPACITY_WARN = 0.45
CENTER_TOLERANCE = 0.12
HUES_LIMIT = 5
PALETTE_DRIFT = 60.0

CONTENT_TYPES = ("text", "image", "progress")
DECOR_TYPES = ("shape", "svg", "asset")


def element_role(element):
    """Declared role, or the type default: content vs decorative."""
    declared = element.get("role")
    if declared in {"content", "decor"}:
        return declared
    return "content" if element.get("type") in CONTENT_TYPES else "decor"


def is_content(element):
    return element_role(element) == "content" and element.get("type") != "progress"


def text_role(element):
    """Return (role, declared) for a text element, inferring from its id."""
    declared = element.get("textRole")
    if declared in TEXT_ROLE_FLOORS:
        return declared, True
    identifier = str(element.get("textId") or element.get("id") or "").upper()
    for token, role in TEXT_ROLE_TOKENS:
        if token in identifier:
            return role, False
    return DEFAULT_TEXT_ROLE, False


def text_floor(element, page_type=None):
    """Font floor in preview pixels, raised on title and TOC pages."""
    role, _ = text_role(element)
    floor = TEXT_ROLE_FLOORS[role]
    if page_type == "title":
        if role == "title":
            floor = max(floor, TITLE_PAGE_TITLE_MIN)
        elif role in {"subtitle", "section"}:
            floor = max(floor, TITLE_PAGE_SUBTITLE_MIN)
    elif page_type == "thanks":
        floor = max(floor, TITLE_PAGE_TITLE_MIN)
    elif page_type == "toc":
        if role == "title":
            floor = max(floor, TOC_HEADING_MIN)
        elif role in {"subtitle", "section", "body", "label"}:
            floor = max(floor, TOC_ENTRY_MIN)
    return floor
