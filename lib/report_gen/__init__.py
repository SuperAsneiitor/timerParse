from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from .base import TimingReportTemplate
from .format1 import Format1Report
from .format2 import Format2Report
from .pt import PtReport


def create_generator(format_name: str) -> TimingReportTemplate:
    key = (format_name or "").strip().lower()
    if key in ("format2",):
        return Format2Report()
    if key in ("format1", "apr"):
        return Format1Report()
    if key in ("pt",):
        return PtReport()
    raise ValueError(f"Unsupported format: {format_name}")


def run_gen_report(args) -> int:
    """CLI：从 YAML 生成 timing report（使用模板类）。"""
    config_path = getattr(args, "config", "")
    if not config_path:
        print("Error: missing config", file=sys.stderr)
        return 1
    try:
        # 先读取 YAML，拿到 format
        import yaml  # type: ignore
    except Exception:
        print("Error: 需要 PyYAML。请执行: pip install pyyaml", file=sys.stderr)
        return 1
    try:
        text = Path(config_path).read_text(encoding="utf-8")
        config: dict[str, Any] = yaml.safe_load(text) or {}
    except Exception as e:
        print(f"Error: 解析 YAML 失败: {e}", file=sys.stderr)
        return 1

    fmt = str((config.get("format") or "unknown")).strip().lower()
    gen = create_generator(fmt)
    seed = getattr(args, "seed", None)
    output = getattr(args, "output", None) or f"output/gen_{fmt}_timing_report.rpt"
    try:
        gen.generate(config, output_path=output, seed=seed)
    except Exception as e:
        print(f"Error: 生成报告失败: {e}", file=sys.stderr)
        return 1
    print(f"Generated timing report -> {output}")
    return 0


__all__ = ["TimingReportTemplate", "create_generator", "run_gen_report"]

