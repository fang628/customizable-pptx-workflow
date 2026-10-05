"""Remove the flat background around an AI asset so it never lands as a square.

The same algorithm is used by `cutout_asset.py`
(transparent PNG for the PPTX), so the approved preview and the build agree.
"""

from __future__ import annotations

from collections import deque

from PIL import Image, ImageChops, ImageDraw, ImageFilter

DEFAULT_TOLERANCE = 28
DEFAULT_FEATHER = 2


def _rgb(value, default=(255, 255, 255)):
    if isinstance(value, (tuple, list)) and len(value) == 3:
        return tuple(int(channel) for channel in value)
    text = str(value or "").lstrip("#")
    if len(text) != 6:
        return default
    try:
        return tuple(int(text[index:index + 2], 16) for index in (0, 2, 4))
    except ValueError:
        return default


def border_color(image, inset=0):
    """Median colour of the outermost ring, used as the background estimate."""
    rgb = image.convert("RGB")
    width, height = rgb.size
    if width < 2 or height < 2:
        return (255, 255, 255)
    pixels = (
        list(rgb.crop((0, 0, width, 1)).getdata())
        + list(rgb.crop((0, height - 1, width, height)).getdata())
        + list(rgb.crop((0, 0, 1, height)).getdata())
        + list(rgb.crop((width - 1, 0, width, height)).getdata())
    )
    if not pixels:
        return (255, 255, 255)
    channels = []
    for index in range(3):
        values = sorted(pixel[index] for pixel in pixels)
        channels.append(values[len(values) // 2])
    return tuple(channels)


def close_mask(image, background, tolerance):
    """L mask: 255 where the pixel is within `tolerance` of the background."""
    bands = image.convert("RGB").split()
    masks = []
    for band, value in zip(bands, _rgb(background)):
        low, high = max(0, value - tolerance), min(255, value + tolerance)
        masks.append(
            band.point(lambda channel, lo=low, hi=high: 255 if lo <= channel <= hi else 0)
        )
    mask = masks[0]
    for extra in masks[1:]:
        mask = ImageChops.multiply(mask, extra)
    return mask


def border_connected(mask, scale=4):
    """Keep only the parts of `mask` connected to the border, computed downscaled."""
    width, height = mask.size
    small = mask.resize(
        (max(2, width // scale), max(2, height // scale)),
        Image.Resampling.BOX,
    )
    small_width, small_height = small.size
    data = small.load()
    visited = bytearray(small_width * small_height)
    queue = deque()

    def push(x, y):
        index = y * small_width + x
        if not visited[index] and data[x, y] >= 200:
            visited[index] = 1
            queue.append((x, y))

    for x in range(small_width):
        push(x, 0)
        push(x, small_height - 1)
    for y in range(small_height):
        push(0, y)
        push(small_width - 1, y)
    while queue:
        x, y = queue.popleft()
        for next_x, next_y in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= next_x < small_width and 0 <= next_y < small_height:
                push(next_x, next_y)
    grown = Image.new("L", (small_width, small_height), 0)
    grown.putdata([255 if flag else 0 for flag in visited])
    return grown.resize((width, height), Image.Resampling.BILINEAR)


def cutout_foreground(image, tolerance=DEFAULT_TOLERANCE, feather=DEFAULT_FEATHER, background=None):
    """Return the asset with its flat background removed and a soft edge."""
    rgba = image.convert("RGBA")
    if rgba.width < 4 or rgba.height < 4:
        return rgba
    reference = _rgb(background) if background else border_color(rgba)
    close = close_mask(rgba, reference, max(0, int(tolerance)))
    if close.getbbox() is None:
        return rgba
    background_area = border_connected(close)
    keep = ImageChops.invert(background_area)
    keep = keep.filter(ImageFilter.GaussianBlur(float(feather))) if feather else keep
    result = rgba.copy()
    result.putalpha(ImageChops.multiply(rgba.getchannel("A"), keep))
    return result


def edge_transform(element):
    """Normalize the `edge` field; legacy `cutout` keeps working unchanged."""
    value = element.get("edge")
    cutout = cutout_transform(element)
    if value is True:
        value = {}
    if isinstance(value, dict):
        mode = value.get("mode", "cutout")
        if mode not in {"none", "cutout", "feather"}:
            mode = "cutout"
        if mode == "cutout":
            return {
                "mode": "cutout",
                "tolerance": int(
                    value.get(
                        "tolerance",
                        (cutout or {}).get("tolerance", DEFAULT_TOLERANCE),
                    )
                ),
                "feather": float(
                    value.get("feather", (cutout or {}).get("feather", DEFAULT_FEATHER))
                ),
                "radius": float(value.get("radius", 0.20)),
                "edges": list(value.get("edges") or ALL_EDGES),
                "background": value.get("background")
                or (cutout or {}).get("background"),
            }
        return {
            "mode": mode,
            "tolerance": int(value.get("tolerance", DEFAULT_TOLERANCE)),
            "feather": float(value.get("feather", 40)),
            "radius": float(value.get("radius", 0.20)),
            "edges": list(value.get("edges") or ALL_EDGES),
            "background": value.get("background"),
        }
    if cutout:
        return {
            "mode": "cutout",
            "tolerance": int(cutout.get("tolerance", DEFAULT_TOLERANCE)),
            "feather": float(cutout.get("feather", DEFAULT_FEATHER)),
            "radius": 0.20,
            "edges": list(ALL_EDGES),
            "background": cutout.get("background"),
        }
    return {
        "mode": "none",
        "tolerance": DEFAULT_TOLERANCE,
        "feather": 0.0,
        "radius": 0.20,
        "edges": list(ALL_EDGES),
        "background": None,
    }


def edge_mode(element):
    return edge_transform(element)["mode"]


ALL_EDGES = ("left", "right", "top", "bottom")


def feather_edges(image, radius=0.20, feather=40, canvas=None, edges=None):
    """Keep the background but fade the edges so a photo blends into the page.

    ``edges`` limits the fade to the named sides, so a cover hero can feather
    only its left edge while still bleeding off the top, right and bottom.
    """
    rgba = image.convert("RGBA")
    width, height = rgba.size
    if width < 8 or height < 8:
        return rgba
    inset = max(0, round(min(width, height) * max(0.0, min(0.45, float(radius)))))
    selected = tuple(edge for edge in ALL_EDGES if not edges or edge in set(edges))
    if not selected:
        return rgba
    insets = {edge: (inset if edge in selected else 0) for edge in ALL_EDGES}
    mask = Image.new("L", (width, height), 0)
    box = (
        insets["left"],
        insets["top"],
        width - 1 - insets["right"],
        height - 1 - insets["bottom"],
    )
    if len(selected) == len(ALL_EDGES):
        corner = max(2, min(width, height) // 10)
        ImageDraw.Draw(mask).rounded_rectangle(box, radius=corner, fill=255)
    else:
        ImageDraw.Draw(mask).rectangle(box, fill=255)
    if feather:
        mask = mask.filter(ImageFilter.GaussianBlur(float(feather)))
    result = rgba.copy()
    result.putalpha(ImageChops.multiply(rgba.getchannel("A"), mask))
    return result


def apply_asset_edge(image, element):
    """Dispatch the three insertion modes: plain, cutout (no background), feather."""
    transform = edge_transform(element)
    if transform["mode"] == "cutout":
        return apply_cutout(
            image,
            {
                "mode": "edge",
                "tolerance": transform["tolerance"],
                "feather": min(12.0, float(transform["feather"])),
                "background": transform["background"],
            },
        )
    if transform["mode"] == "feather":
        return feather_edges(
            image,
            transform["radius"],
            transform["feather"],
            edges=transform.get("edges"),
        )
    return image


def cutout_transform(element):
    """Normalize an asset `cutout` field for rendering and provenance."""
    value = element.get("cutout")
    if value is None or value is False:
        return None
    if value is True:
        value = {}
    if not isinstance(value, dict):
        return None
    return {
        "mode": value.get("mode", "edge"),
        "tolerance": int(value.get("tolerance", DEFAULT_TOLERANCE)),
        "feather": float(value.get("feather", DEFAULT_FEATHER)),
        "background": value.get("background"),
    }


def apply_cutout(image, transform):
    if not transform or transform.get("mode", "edge") != "edge":
        return image
    return cutout_foreground(
        image,
        transform.get("tolerance", DEFAULT_TOLERANCE),
        transform.get("feather", DEFAULT_FEATHER),
        transform.get("background"),
    )
