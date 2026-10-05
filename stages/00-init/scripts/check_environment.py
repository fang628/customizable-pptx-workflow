#!/usr/bin/env python3
"""Report available local dependencies without reading credential values."""

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "shared/scripts"))

from text_metrics import canonical_family, font_status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", default="node")
    parser.add_argument("--project")
    parser.add_argument("--qwen-script")
    parser.add_argument("--adapter-script")
    parser.add_argument(
        "--font",
        action="append",
        default=[],
        help="必需字体族，可重复；缺失时返回非零退出码",
    )
    args = parser.parse_args()
    result = {"python": sys.version.split()[0], "dependencies": {}, "warnings": []}
    for name, expected in [("jsonschema", "4.26.0"), ("Pillow", "12.3.0")]:
        try:
            version = importlib.metadata.version(name)
            result["dependencies"][name] = version
            if version != expected:
                result["warnings"].append(f"{name} 已安装 {version}，测试版本为 {expected}")
        except importlib.metadata.PackageNotFoundError:
            result["dependencies"][name] = None
    code = "const p=require('path'); const paths=[p.join(process.cwd(),'node_modules'),process.env.CODEX_NODE_MODULES,p.join(require('os').homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules')].filter(Boolean); for(const name of ['pptxgenjs','sharp']) { const file=paths.map(d=>p.join(d,name,'package.json')).find(f=>require('fs').existsSync(f)); if(file) console.log(name+': '+require(file).version); else { console.log(name+': MISSING'); process.exitCode=1 } }"
    try:
        process = subprocess.run([args.node, "-e", code], cwd=Path(__file__).resolve().parents[3], capture_output=True, text=True)
        result["node_modules"] = process.stdout.strip()
        result["node_ready"] = process.returncode == 0
    except OSError:
        result["node_ready"] = False
    result["libreoffice"] = shutil.which("soffice")
    if os.name == "nt":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "PowerPoint.Application"):
                result["powerpoint_registered"] = True
        except OSError:
            result["powerpoint_registered"] = False
        result["microsoft_yahei_font_file"] = (Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/msyh.ttc").is_file()
    config_path = None
    if args.project:
        config_path = Path(args.project).expanduser().resolve() / "00_intake/ai-image-config.json"
    if config_path and config_path.is_file():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8-sig"))
            credential_env = config.get("credentialEnv")
            adapter_script = args.adapter_script or config.get("adapterScript")
            if not adapter_script and config.get("provider") == "qwen":
                candidates = [
                    Path.home() / ".codex/skills/qwen-imagegen/scripts/qwen_imagegen.py",
                    Path.home() / ".codex/skills/qwen-imagegen/scripts/qwen_image_gen.py",
                ]
                adapter_script = next((str(path) for path in candidates if path.is_file()), "")
            if not adapter_script and config.get("provider") in {"vsakura", "gpt-image", "openai-images"}:
                candidates = [
                    Path.home() / ".codex/skills/vsakura-imagegen/scripts/vsakura_imagegen.py",
                ]
                adapter_script = next((str(path) for path in candidates if path.is_file()), "")
            result["ai_image_config"] = {
                "path": str(config_path),
                "valid_json": True,
                "provider": config.get("provider"),
                "model": config.get("model"),
                "credentialsReady": config.get("credentialsReady") is True,
                "credentialEnv": credential_env,
                "credentialPresent": bool(
                    isinstance(credential_env, str)
                    and credential_env
                    and os.environ.get(credential_env)
                ),
                "allowReferenceUpload": config.get("allowReferenceUpload") is True,
                "budgetsEnabled": False,
                "note": "生图不设次数预算；stageBudgets 若存在也仅作兼容保留，脚本忽略其取值。",
                "adapterScript": adapter_script or None,
                "adapterScriptExists": bool(adapter_script and Path(adapter_script).expanduser().is_file()),
            }
        except (OSError, ValueError, TypeError) as exc:
            result["ai_image_config"] = {
                "path": str(config_path),
                "valid_json": False,
                "error": f"配置无法读取：{exc}",
            }
            result["warnings"].append("AI 生图配置无法读取；阶段 1.1 必须修复后再完成。")
    else:
        result["ai_image_config"] = {
            "path": str(config_path) if config_path else None,
            "valid_json": False,
            "error": "未找到项目 AI 生图配置；运行阶段 0 初始化器创建模板。",
        }
        result["warnings"].append("未找到 AI 生图配置；阶段 1.1 必须完成配置。")
    if args.qwen_script:
        result["legacy_qwen_script"] = str(Path(args.qwen_script).expanduser().resolve())
        result["qwen_script_exists"] = Path(args.qwen_script).expanduser().is_file()
    inventory = font_status()
    fonts = {
        "directory": str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"),
        "families": inventory,
        "ready": True,
    }
    if args.font:
        missing = [
            name
            for name in args.font
            if not inventory.get(canonical_family(name), {}).get("ready")
        ]
        fonts["required"] = list(args.font)
        fonts["missing"] = missing
        fonts["ready"] = not missing
        if missing:
            result["warnings"].append(
                "缺少必需字体："
                + "、".join(missing)
                + "；预览会改用替代字体，字号与换行必须在渲染中确认，或更换已安装的字体"
            )
    result["fonts"] = fonts
    if args.project:
        project = Path(args.project).expanduser().resolve()
        intake = project / "00_intake"
        if intake.is_dir():
            report_path = intake / "font-report.json"
            report_path.write_text(
                json.dumps(fonts, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            fonts["reportPath"] = "00_intake/font-report.json"
    result["warnings"].append(
        "字体清单只覆盖已知中英文字体族，不代表系统全部字体；未读取或输出 API 密钥。"
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    ready = result["node_ready"] and all(result["dependencies"].values())
    if args.font and not fonts["ready"]:
        ready = False
    return 0 if ready else 1


if __name__ == "__main__":
    sys.exit(main())
