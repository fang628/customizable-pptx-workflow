"""Local image-provider fixture. Never contacts a remote service."""

import argparse
import json
from pathlib import Path
import sys
import uuid

from PIL import Image, ImageDraw

parser = argparse.ArgumentParser()
parser.add_argument("--prompt")
parser.add_argument("--model", default="gpt-image-2")
parser.add_argument("--output-dir")
args, _ = parser.parse_known_args()
if (args.prompt or "").startswith("FAIL"):
    print(json.dumps({"success": False, "error": "SENSITIVE_TEST_MARKER"}))
    sys.exit(1)
if (args.prompt or "").startswith("FLAKY"):
    # Fail the first two attempts, then succeed: exercises the retry loop.
    marker = Path(args.output_dir).resolve() / "attempts.txt"
    marker.parent.mkdir(parents=True, exist_ok=True)
    attempts = len(marker.read_text(encoding="utf-8").splitlines()) if marker.exists() else 0
    marker.write_text("\n".join(["attempt"] * (attempts + 1)) + "\n", encoding="utf-8")
    if attempts < 2:
        print(json.dumps({"success": False, "error": "transient failure"}))
        sys.exit(1)
if (args.prompt or "").startswith("BACKGROUND"):
    # Calm page background: pale field, soft off-centre shapes, empty middle.
    size = (960, 540)
    image = Image.new("RGB", size, "#F2EFE9")
    draw = ImageDraw.Draw(image)
    draw.ellipse((-140, -160, 260, 200), fill="#E7E2D8")
    draw.ellipse((700, 380, 1080, 700), fill="#EAE4D9")
    draw.rectangle((0, 470, 960, 540), fill="#EFEBE2")
    marker = Path(args.output_dir).resolve() / "mock.png"
    marker.parent.mkdir(parents=True, exist_ok=True)
    image.save(marker)
    print(json.dumps({
        "success": True,
        "model": args.model,
        "request_id": f"mock-{uuid.uuid4().hex}",
        "output_files": [str(marker)],
    }))
    sys.exit(0)

def placeholder_boxes(prompt):
    """测试夹具：从提示词的「占位块框：」里读出要画的占位块（归一化坐标）。"""
    marker = "占位块框："
    if marker not in prompt:
        return []
    spec = prompt.split(marker, 1)[1].split("；", 1)[0]
    boxes = []
    for item in spec.split("，"):
        _, _, numbers = item.partition("=")
        parts = numbers.split(",")
        if len(parts) == 4:
            boxes.append(tuple(float(value) for value in parts))
    return boxes


path = Path(args.output_dir).resolve() / "mock.png"
path.parent.mkdir(parents=True, exist_ok=True)
size = (640, 640) if ((args.prompt or "").startswith("SQUARE") or "RETURN-SQUARE" in (args.prompt or "")) else (640, 360)
# A subject on a flat background, so cutout and masking stay testable.
image = Image.new("RGB", size, "#FFFFFF")
draw = ImageDraw.Draw(image)
inset = int(min(size) * 0.18)
draw.ellipse(
    (inset, inset, size[0] - inset, size[1] - inset),
    fill="#27776B",
)
draw.rectangle(
    (int(size[0] * 0.42), int(size[1] * 0.42), int(size[0] * 0.58), int(size[1] * 0.58)),
    fill="#E76F51",
)
# Whole-page previews keep planned photos/data charts as flat placeholder blocks.
for x, y, w, h in placeholder_boxes(args.prompt or ""):
    draw.rectangle(
        (
            int(round(x * size[0])),
            int(round(y * size[1])),
            int(round((x + w) * size[0])),
            int(round((y + h) * size[1])),
        ),
        fill="#D6DEE6",
        outline="#8C97A3",
        width=3,
    )
image.save(path)
print(json.dumps({
    "success": True,
    "model": args.model,
    "request_id": f"mock-{uuid.uuid4().hex}",
    "output_files": [str(path)],
}))
