"""Validate final previews and normalize raw provider assets."""

from pathlib import Path
import time

from PIL import Image, ImageOps


def _replace(temporary, path, attempts=6, delay=0.05):
    """Atomically move a temporary file into place, tolerating Windows file locks."""
    for attempt in range(attempts):
        try:
            Path(temporary).replace(path)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay * (attempt + 1))


def image_errors(path):
    """Validate a final composed preview, which must be an exact 1920x1080 PNG."""
    try:
        with Image.open(path) as image:
            image.load()
            if image.format != "PNG":
                return [f"预览必须为真实 PNG 文件：{path}"]
            if image.size != (1920, 1080):
                return [f"最终预览必须为精确 1920x1080，实际 {image.width}x{image.height}：{path}"]
    except (OSError, ValueError) as exc:
        return [f"预览图无法解码：{path}：{exc}"]
    return []


def asset_image_errors(path):
    """Validate an AI-generated source asset; its aspect ratio is intentionally free."""
    try:
        with Image.open(path) as image:
            image.load()
            if image.format != "PNG":
                return [f"AI 素材必须输出为 PNG 文件：{path}"]
    except (OSError, ValueError) as exc:
        return [f"AI 素材无法解码：{path}：{exc}"]
    return []


def stage_preview_errors(project, stage):
    errors = []
    if stage == "2.1":
        for option in "abc":
            paths = sorted(project.glob(f"03_concepts/option-{option}/*.png"))
            if not 1 <= len(paths) <= 3:
                errors.append(f"方案 {option} 必须包含 1 至 3 页 PNG")
            for path in paths:
                errors += image_errors(path)
    elif stage == "2.2":
        from workflow_lib import read_json
        expected = {s["id"] for s in read_json(project / "02_design/content.json")["slides"]}
        paths = sorted(project.glob("04_full-preview/slides/*.png"))
        if {path.stem for path in paths} != expected:
            errors.append("完整预览与定稿页面编号不一致")
        for path in paths:
            errors += image_errors(path)
    return errors


def _opaque(image, background):
    opaque = Image.new("RGBA", image.size, background)
    opaque.alpha_composite(image)
    return opaque.convert("RGB")


def normalize_asset(source, output, mode="preserve", size=None, background="#FFFFFF"):
    """Normalize one independent AI asset without imposing a page aspect ratio."""
    source, output = Path(source), Path(output)
    if source.resolve() == output.resolve():
        raise ValueError("不能覆盖原始生成图")
    if output.suffix.lower() != ".png":
        raise ValueError("AI 素材输出必须使用 .png 后缀")
    if mode not in {"preserve", "pad", "crop"}:
        raise ValueError("素材比例处理仅支持 preserve、pad、crop")
    with Image.open(source) as original:
        image = ImageOps.exif_transpose(original).convert("RGBA")
    original_size = list(image.size)
    image = _opaque(image, background)
    target = None
    if mode != "preserve":
        if not isinstance(size, (list, tuple)) or len(size) != 2:
            raise ValueError("pad/crop 模式必须指定二元素 asset_size")
        target = (int(size[0]), int(size[1]))
        if target[0] < 1 or target[1] < 1:
            raise ValueError("asset_size 必须为正整数")
    if mode == "crop":
        result = ImageOps.fit(image, target, method=Image.Resampling.LANCZOS)
    elif mode == "pad":
        fitted = ImageOps.contain(image, target, method=Image.Resampling.LANCZOS)
        result = Image.new("RGB", target, background)
        result.paste(fitted, ((target[0] - fitted.width) // 2, (target[1] - fitted.height) // 2))
    else:
        result = image
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp.png")
    result.save(temporary, format="PNG")
    _replace(temporary, output)
    return {
        "original_size": original_size,
        "output_size": list(result.size),
        "mode": mode,
        "background": background,
        "target_size": list(target) if target else None,
    }


def normalize(source, output, mode="strict", background="#FFFFFF"):
    """Normalize a raw provider image into a final 1920x1080 preview."""
    source, output = Path(source), Path(output)
    if source.resolve() == output.resolve():
        raise ValueError("不能覆盖原始生成图")
    if output.suffix.lower() != ".png":
        raise ValueError("预览输出必须使用 .png 后缀")
    if mode not in {"pad", "crop", "strict"}:
        raise ValueError("比例处理仅支持 pad、crop、strict")
    with Image.open(source) as original:
        image = ImageOps.exif_transpose(original).convert("RGBA")
    original_size = list(image.size)
    image = _opaque(image, background)
    exact = image.width * 9 == image.height * 16
    if not exact:
        raise ValueError(f"整页原图不是精确 16:9，退回：{image.width}x{image.height}；不得裁切或补边修正比例")
    result = image.resize((1920, 1080), resample=Image.Resampling.LANCZOS)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp.png")
    result.save(temporary, format="PNG")
    _replace(temporary, output)
    return {"original_size": original_size, "output_size": [1920, 1080],
            "mode": "proportional_resize" if exact else mode, "background": background}
