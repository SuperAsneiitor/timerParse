from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from .base import TimingReportTemplate
from .format1 import Format1Report
from .format2 import Format2Report
from .pt import PtReport
from .. import log_util


def create_generator(format_name: str) -> TimingReportTemplate:
    key = (format_name or "").strip().lower()
    if key in ("format2",):
        return Format2Report()
    if key in ("format1", "apr"):
        return Format1Report()
    if key in ("pt",):
        return PtReport()
    raise ValueError(f"Unsupported format: {format_name}")


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(out.get(k), dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _load_yaml_file(path: Path) -> dict[str, Any]:
    import yaml  # type: ignore

    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(text) or {}


def _load_with_extends(config_path: Path) -> dict[str, Any]:
    cfg = _load_yaml_file(config_path)
    extends = cfg.get("extends")
    if not extends:
        return cfg
    base_path = (config_path.parent / str(extends)).resolve()
    base_cfg = _load_with_extends(base_path)
    child_cfg = dict(cfg)
    child_cfg.pop("extends", None)
    return _deep_merge(base_cfg, child_cfg)


def _profiles_to_when_type(
    columns: dict[str, dict[str, Any]],
    row_type_profiles: dict[str, list[str]],
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for col, cfg in (columns or {}).items():
        cc = dict(cfg or {})
        profiles = cc.pop("profiles", None)
        if profiles:
            names = profiles if isinstance(profiles, list) else [profiles]
            when: list[str] = []
            for name in names:
                vals = row_type_profiles.get(str(name), [])
                if isinstance(vals, list):
                    when.extend([str(x) for x in vals])
            if when:
                # 去重并保持原顺序
                cc["when_type"] = list(dict.fromkeys(when))
        out[col] = cc
    return out


def _normalize_config_schema(config: dict[str, Any]) -> dict[str, Any]:
    """
    支持新 schema（variables/structure/table + row_type_profiles + summary_policy）
    并归一化为现有生成器可消费的 legacy schema（path_vars/path_table/...）。
    """
    cfg = copy.deepcopy(config or {})
    row_profiles = cfg.get("row_type_profiles") or {}

    # legacy schema：仅补齐 profiles -> when_type
    if "path_table" in cfg:
        pt = dict(cfg.get("path_table") or {})
        cols = _profiles_to_when_type(pt.get("columns") or {}, row_profiles)
        if cols:
            pt["columns"] = cols
        cfg["path_table"] = pt
        return cfg

    # new schema -> legacy
    out: dict[str, Any] = {
        "format": cfg.get("format", ""),
        "num_paths": cfg.get("num_paths", 1),
        "path_vars": cfg.get("variables") or cfg.get("path_vars") or {},
        "point_generator": cfg.get("point_generator") or {},
        "title": cfg.get("title") or {"attributes": []},
    }
    table = cfg.get("table") or {}
    structure = cfg.get("structure") or {}
    path_table: dict[str, Any] = {
        "column_order": table.get("column_order") or [],
        "columns": _profiles_to_when_type(table.get("columns") or {}, row_profiles),
        "cumulative_rules": table.get("cumulative_rules") or table.get("accumulate") or {},
        "row_templates": structure.get("launch") or [],
        "capture_row_templates": structure.get("capture") or [],
        "separator": table.get("separator", ""),
        "column_widths": table.get("column_widths") or {},
        "slack_line": bool(table.get("slack_line", False)),
    }
    out["path_table"] = path_table
    if "summary_policy" in cfg:
        out["summary_policy"] = cfg.get("summary_policy") or {}
    return out


def run_gen_report(args) -> int:
    """CLI：从 YAML 生成 timing report（使用模板类）。"""
    config_path = getattr(args, "config", "")
    if not config_path:
        log_util.error("Error: missing config")
        return 1
    try:
        # 先读取 YAML，拿到 format
        import yaml  # type: ignore
    except Exception:
        log_util.error("Error: 需要 PyYAML。请执行: pip install pyyaml")
        return 1
    try:
        raw_config = _load_with_extends(Path(config_path).resolve())
        config: dict[str, Any] = _normalize_config_schema(raw_config)
    except Exception as e:
        log_util.error(f"Error: 解析 YAML 失败: {e}")
        return 1

    fmt = str((config.get("format") or "unknown")).strip().lower()
    gen = create_generator(fmt)
    seed = getattr(args, "seed", None)
    output = getattr(args, "output", None) or f"output/gen_{fmt}_timing_report.rpt"
    try:
        gen.generate(config, output_path=output, seed=seed)
    except Exception as e:
        log_util.error(f"Error: 生成报告失败: {e}")
        return 1
    num_paths = int(config.get("num_paths", 0))
    log_util.brief(f"Generated timing report -> {output}")
    log_util.full(f"  config: {config_path}")
    log_util.full(f"  format: {fmt}, num_paths: {num_paths}")
    log_util.full(f"  output: {output}")
    return 0


__all__ = ["TimingReportTemplate", "create_generator", "run_gen_report"]

