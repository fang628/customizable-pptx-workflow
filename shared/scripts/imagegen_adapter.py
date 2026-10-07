"""Provider-neutral CLI adapter for image-generation skills."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


DEFAULT_ARGUMENTS = {
    "prompt": "--prompt",
    "model": "--model",
    "size": "--size",
    "count": "--n",
    "seed": "--seed",
    "outputDir": "--output-dir",
    "image": "--image",
}


def _default_script(provider):
    candidates = []
    if provider == "qwen":
        candidates = [
            Path.home() / ".codex/skills/qwen-imagegen/scripts/qwen_imagegen.py",
            Path.home() / ".codex/skills/qwen-imagegen/scripts/qwen_image_gen.py",
        ]
    elif provider in {"vsakura", "gpt-image", "openai-images"}:
        candidates = [
            Path.home() / ".codex/skills/vsakura-imagegen/scripts/vsakura_imagegen.py",
        ]
    return next((path for path in candidates if path.is_file()), None)


def resolve_script(config, override=None):
    if config.get("provider") == "imagegen":
        if override or config.get("adapterScript"):
            raise ValueError("内置 imagegen 不接受 CLI 脚本覆盖；更换通道须先更新并确认配置")
        return Path(__file__).with_name("builtin_imagegen.py")
    value = override or config.get("adapterScript")
    if value:
        path = Path(value).expanduser().resolve()
    else:
        path = _default_script(config["provider"])
        if path is None:
            raise ValueError(
                f"provider={config['provider']} 未配置 adapterScript；"
                "该 provider 必须提供兼容的 CLI JSON 生图脚本"
            )
    if not path.is_file():
        raise ValueError(f"生图适配脚本不存在：{path}")
    return path


def build_command(config, request, python=None, script_override=None):
    """Build a provider CLI command from the configured argument mapping."""
    if config.get("provider") == "imagegen":
        raise ValueError("内置 imagegen 必须由代理调用 image_gen 工具，随后用 --import-result 登记；不能通过 CLI 调用或静默切换 API")
    script = resolve_script(config, script_override)
    arguments = {**DEFAULT_ARGUMENTS, **config.get("adapterArguments", {})}
    executable = config.get("adapterPython") or python or sys.executable
    command = [
        executable,
        str(script),
        arguments["prompt"],
        request["prompt"],
        arguments["model"],
        config["model"],
        arguments["size"],
        request["size"],
        arguments["count"],
        "1",
        arguments["outputDir"],
        str(request["output_dir"]),
    ]
    if "seed" in request:
        command += [arguments["seed"], str(request["seed"])]
    for reference in request.get("references", []):
        command += [arguments["image"], str(reference)]
    return command, script


def _json_object(stdout):
    try:
        value = json.loads(stdout)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def call_provider(config, request, python=None, script_override=None, timeout=300):
    """Call the configured CLI and return a deliberately small metadata envelope."""
    command, script = build_command(config, request, python=python, script_override=script_override)
    try:
        process = subprocess.run(
            command,
            capture_output=True,
            encoding="utf-8",
            timeout=timeout,
            env={**os.environ, "PYTHONUTF8": "1"},
        )
    except subprocess.TimeoutExpired as exc:
        # 系统休眠会让单调时钟跳变，Python 会按负的剩余时间判超时；
        # 这里给出可读原因，交给上层重试而不是中断整轮。
        note = "（检测到本地时钟跳变，可能是系统休眠）" if (exc.timeout or 0) < 0 else ""
        raise ValueError(f"生成服务调用超过 {timeout} 秒未返回{note}") from exc
    payload = _json_object(process.stdout)
    if process.returncode or not payload or payload.get("success") is not True:
        raise ValueError("生成服务返回失败")
    output_files = payload.get("output_files")
    if not isinstance(output_files, list) or len(output_files) != 1:
        raise ValueError("输出图数量与任务不一致")
    request_id = payload.get("request_id") or payload.get("call_id")
    if not isinstance(request_id, str) or not request_id.strip():
        raise ValueError("生成服务未返回可追溯的 request_id")
    actual_model = payload.get("model")
    if not isinstance(actual_model, str) or not actual_model.strip():
        raise ValueError("生成服务未返回实际模型名称")
    if actual_model != config["model"]:
        raise ValueError(
            f"生成服务实际模型为 {actual_model}，与配置的 {config['model']} 不一致；"
            "禁止静默切换到其他模型"
        )
    return {
        "request_id": request_id,
        "model": actual_model,
        "protocol": payload.get("protocol") if isinstance(payload.get("protocol"), str) else "cli-json",
        "output_files": [Path(value) for value in output_files if isinstance(value, str)],
        "adapter_script": script,
    }
