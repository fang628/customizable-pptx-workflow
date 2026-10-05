"""Normalize a raw provider output as an independent AI preview asset."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared/scripts"))
from preview_images import normalize_asset
from workflow_lib import digest, write_json

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--mode", choices=["preserve", "pad", "crop"], default="preserve")
    parser.add_argument("--size", help="pad/crop 目标尺寸，例如 1200x800")
    parser.add_argument("--background", default="#FFFFFF")
    args = parser.parse_args()
    try:
        size = None
        if args.size:
            try:
                size = [int(value) for value in args.size.lower().split("x", 1)]
            except ValueError:
                raise ValueError("--size 必须为 WIDTHxHEIGHT") from None
        record = normalize_asset(args.source, args.output, args.mode, size, args.background)
        record.update(source=str(args.source.resolve()), source_sha256=digest(args.source), output_sha256=digest(args.output))
        write_json(args.output.with_suffix(".normalization.json"), record)
        print("已输出独立 AI 素材；最终预览仍须由本地合成器组装为 1920x1080。")
    except (OSError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        sys.exit(1)
