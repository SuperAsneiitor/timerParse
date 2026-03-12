"""
根据 YAML 配置生成 Timing 报告。

流程：
1. 生成每条 path 的 Title（Scenario、Path Start、Path End、Common Pin、Group Name、Analysis Type 等）
   - 用户可指定属性名、值的格式（浮点、字符串、枚举）及类型（固定值、随机等）
2. 生成 Timing path 报告表格
   - 用户提供各属性名与值配置，可自定义列顺序
"""
from __future__ import annotations

import random
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]


# ---------- 值解析 ----------

def _resolve_value(spec: dict[str, Any], ctx: dict[str, Any]) -> str | float | int:
    """根据 value_spec 与上下文解析出最终值。返回可格式化为字符串的类型。"""
    if not isinstance(spec, dict):
        return str(spec)
    kind = (spec.get("type") or spec.get("kind") or "fixed").strip().lower()
    if kind == "fixed":
        v = spec.get("value", "")
        return v if isinstance(v, (int, float)) else str(v)
    if kind == "enum":
        choices = spec.get("choices") or spec.get("options") or []
        if not choices:
            return ""
        weights = spec.get("weights")
        if weights and len(weights) == len(choices):
            return str(random.choices(choices, weights=weights, k=1)[0])
        return str(random.choice(choices))
    if kind == "random_float":
        lo = float(spec.get("min", 0))
        hi = float(spec.get("max", 1))
        decimals = int(spec.get("decimals", 3))
        v = random.uniform(lo, hi)
        return round(v, decimals)
    if kind == "random_int":
        lo = int(spec.get("min", 0))
        hi = int(spec.get("max", 10))
        return random.randint(lo, hi)
    if kind == "format" or kind == "template":
        tpl = spec.get("template") or spec.get("format") or spec.get("value") or ""
        return _format_template(tpl, ctx)
    if kind == "ref":
        key = spec.get("ref") or spec.get("field")
        return str(ctx.get(key, ""))
    if kind == "row_type":
        return str(ctx.get("row_type", ""))
    if kind == "sequence":
        start = int(spec.get("start", 1))
        step = int(spec.get("step", 1))
        idx = int(ctx.get("path_index", 0))
        return start + idx * step
    return str(spec.get("value", ""))


def _format_template(tpl: str, ctx: dict[str, Any]) -> str:
    """替换模板中的 {path.xxx}、{row.xxx}、{key} 等占位符。"""
    if not tpl:
        return ""
    text = tpl
    path = ctx.get("path") or {}
    row = ctx.get("row") or {}
    # 单层 path.* / row.*
    for k, v in path.items():
        text = text.replace("{" + f"path.{k}" + "}", str(v))
    for k, v in row.items():
        text = text.replace("{" + f"row.{k}" + "}", str(v))
    # 直接键（含 point_generator 常用变量）
    for key in ("path_id", "path_index", "row_type", "row_index", "startpoint", "endpoint", "clock",
                "scenario", "group_name", "analysis_type", "common_pin", "point", "point_name",
                "point_index", "pin_index_in_launch", "pin_index_in_capture", "prefix", "pin_index",
                "pin_suffix", "pin_pin", "net_index", "clock_index", "segment"):
        val = ctx.get(key) if ctx.get(key) is not None else path.get(key) or row.get(key)
        if val is not None:
            text = text.replace("{" + key + "}", str(val))
    # 兜底：ctx 中其余可字符串化的键也替换（便于 point_generator 使用任意变量）
    for k, v in ctx.items():
        if k in ("path", "row") or "{" + k + "}" not in text:
            continue
        if v is not None and isinstance(v, (str, int, float, bool)):
            text = text.replace("{" + k + "}", str(v))
    return text


def _str_value(v: str | float | int) -> str:
    if isinstance(v, float):
        return f"{v:.3f}" if abs(v) < 1e6 else str(v)
    return str(v)


def _to_float(v: Any) -> float:
    """将值转为 float，用于累加。"""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip())
    except (ValueError, TypeError):
        return 0.0


# ---------- Title 生成 ----------

def _render_title_block(title_config: list[dict], path_ctx: dict[str, Any], format_name: str) -> str:
    """生成单条 path 的 title 块（多行）。"""
    lines = []
    name_width = 24  # 与现有 format2 对齐
    for attr in title_config:
        name = attr.get("name") or attr.get("key") or ""
        spec = attr.get("value") or attr.get("spec") or {}
        ctx = {**path_ctx, "path": path_ctx}
        val = _resolve_value(spec, ctx)
        val_str = _str_value(val)
        if format_name == "format2":
            lines.append(f"  {name:<{name_width}}  :  {val_str}")
        else:
            # format1 / pt 风格简化为 "Name: value"
            lines.append(f"  {name}: {val_str}")
    return "\n".join(lines) + "\n"


# ---------- 表格行生成 ----------

def _render_table_row(
    column_order: list[str],
    columns_config: dict[str, dict],
    row_ctx: dict[str, Any],
    format_name: str,
    col_widths: dict[str, int] | None = None,
    cumulative_targets: set[str] | None = None,
    cumulative_sources: set[str] | None = None,
) -> str:
    """生成一行表格内容；cumulative_targets 的列用 row_ctx 中的累加值；cumulative_sources 的列用 row_ctx 中已写入的增量（与累加一致）。"""
    cells = []
    cumulative_targets = cumulative_targets or set()
    cumulative_sources = cumulative_sources or set()
    for col in column_order:
        cfg = columns_config.get(col) or {}
        when = cfg.get("when_type") or cfg.get("when")
        row_type = row_ctx.get("row_type", "")
        if when and row_type and row_type not in when:
            cells.append("")
            continue
        if col in cumulative_targets and col in row_ctx and row_ctx[col] is not None:
            cells.append(_str_value(row_ctx[col]))
            continue
        if col in cumulative_sources and col in row_ctx and row_ctx[col] is not None:
            cells.append(_str_value(row_ctx[col]))
            continue
        spec = cfg.get("value") or cfg.get("spec") or {}
        ctx = {**row_ctx, "row": row_ctx, "path": row_ctx.get("path") or {}}
        val = _resolve_value(spec, ctx)
        cells.append(_str_value(val))
    if col_widths:
        parts = []
        for i, col in enumerate(column_order):
            w = col_widths.get(col, 20)
            parts.append((cells[i] if i < len(cells) else "").ljust(w)[:w])
        return "".join(parts).rstrip()
    return " ".join(cells)


def _default_column_widths(column_order: list[str], format_name: str) -> dict[str, int]:
    """为 format2 等格式提供默认列宽。"""
    defaults = {
        "Type": 28,
        "Fanout": 10,
        "Cap": 10,
        "D-Trans": 12,
        "Trans": 10,
        "Derate": 14,
        "x-coord": 12,
        "y-coord": 12,
        "D-Delay": 10,
        "Delay": 10,
        "Time": 12,
        "Description": 80,
    }
    return {c: defaults.get(c, 16) for c in column_order}


# ---------- 路径点生成（完整 timing 路径） ----------

def _generate_segment_points(
    segment_rows: list[dict],
    segment_name: str,
    path_ctx: dict[str, Any],
    point_gen_config: dict[str, Any],
    path_index: int,
    seed: int | None,
) -> list[str]:
    """根据 row_templates 与 point_generator 配置，为 launch 或 capture 段生成每行对应的 point 名。"""
    pin_count = sum(1 for r in segment_rows if (r.get("type") or r.get("row_type") or "").strip().lower() == "pin")
    out: list[str] = []
    pin_index = 0
    net_index = 0
    clock_index = 0
    point_index = 0
    for row_tmpl in segment_rows:
        row_type = (row_tmpl.get("type") or row_tmpl.get("row_type") or "pin").strip().lower()
        ctx = {
            **path_ctx,
            "path": path_ctx,
            "row_type": row_type,
            "point_index": point_index,
            "segment": segment_name,
        }
        if row_type == "pin":
            pin_key = "pin_index_in_launch" if segment_name == "launch" else "pin_index_in_capture"
            ctx[pin_key] = pin_index
            ctx["pin_index"] = pin_index
            ctx["is_startpoint"] = segment_name == "launch" and pin_index == 0
            ctx["is_endpoint"] = segment_name == "launch" and pin_index == pin_count - 1
            ctx["pin_suffix"] = "Q" if ctx["is_startpoint"] else ("D" if ctx["is_endpoint"] else "Z")
            ctx["pin_pin"] = ctx["pin_suffix"]
            pin_index += 1
        elif row_type == "net":
            ctx["net_index"] = net_index
            net_index += 1
        elif row_type in ("clock", "port"):
            ctx["clock_index"] = clock_index
            clock_index += 1
        point_index += 1

        gen = point_gen_config.get(row_type) or point_gen_config.get("default") or {}
        if isinstance(gen, str):
            out.append(_format_template(gen, ctx))
            continue
        if not gen:
            out.append("")
            continue
        spec = gen.get("value") or gen.get("template") or gen
        if isinstance(spec, str):
            out.append(_format_template(spec, ctx))
            continue
        tpl = spec.get("template") or spec.get("format") or spec.get("value")
        if tpl:
            out.append(_format_template(tpl, ctx))
            continue
        val = _resolve_value(spec, ctx)
        out.append(_str_value(val))
    return out


def _generate_full_path_points(
    config: dict,
    path_index: int,
    launch_rows: list[dict],
    capture_rows: list[dict],
    seed: int | None,
) -> tuple[list[str], list[str], str, str]:
    """
    为一条 path 生成完整 launch/capture 点序列，并得到 startpoint、endpoint。
    startpoint = launch 段中第一个 pin 行的 point 名，endpoint = launch 段中最后一个 pin 行的 point 名。
    """
    point_gen = config.get("point_generator") or config.get("path_point_generator") or {}
    path_ctx_base: dict[str, Any] = {
        "path_index": path_index,
        "path_id": path_index + 1,
        "clock": "pll_cpu_clk",
        "prefix": f"path_{path_index}",
    }
    path_vars = config.get("path_vars") or config.get("path_variables") or {}
    for key, spec in path_vars.items():
        if key in ("startpoint", "endpoint"):
            continue
        if isinstance(spec, dict):
            path_ctx_base[key] = _resolve_value(spec, path_ctx_base)
        else:
            path_ctx_base[key] = spec
    path_ctx_base.setdefault("prefix", f"path_{path_index}")
    path_ctx_base["path"] = path_ctx_base

    launch_points = _generate_segment_points(
        launch_rows, "launch", path_ctx_base, point_gen, path_index, seed
    )
    capture_points = _generate_segment_points(
        capture_rows, "capture", path_ctx_base, point_gen, path_index, seed
    )

    pin_indices_launch = [i for i, r in enumerate(launch_rows) if (r.get("type") or r.get("row_type") or "").strip().lower() == "pin"]
    if pin_indices_launch and launch_points:
        startpoint = launch_points[pin_indices_launch[0]]
        endpoint = launch_points[pin_indices_launch[-1]]
    else:
        startpoint = path_ctx_base.get("startpoint", "inst/start/Q (CELL)")
        endpoint = path_ctx_base.get("endpoint", "inst/end/D (CELL)")

    return launch_points, capture_points, startpoint, endpoint


# ---------- 主流程 ----------

def _generate_path_meta(
    config: dict,
    path_index: int,
    seed: int | None,
    launch_rows: list[dict],
    capture_rows: list[dict],
) -> dict[str, Any]:
    """为一条 path 生成元数据（用于 title 与表格中的 format/ref）。若配置了 point_generator，则 startpoint/endpoint 与整条路径的 point 均由生成器生成。"""
    if seed is not None:
        random.seed(seed)
    path_ctx: dict[str, Any] = {"path_index": path_index, "path_id": path_index + 1}

    point_gen = config.get("point_generator") or config.get("path_point_generator")
    if point_gen:
        launch_pts, capture_pts, startpoint, endpoint = _generate_full_path_points(
            config, path_index, launch_rows, capture_rows, seed
        )
        path_ctx["launch_points"] = launch_pts
        path_ctx["capture_points"] = capture_pts
        path_ctx["startpoint"] = startpoint
        path_ctx["endpoint"] = endpoint
    else:
        path_ctx["launch_points"] = []
        path_ctx["capture_points"] = []

    # 解析 path_vars（若未用 point_generator 生成 startpoint/endpoint，则这里提供）
    path_vars = config.get("path_vars") or config.get("path_variables") or {}
    for key, spec in path_vars.items():
        if key in path_ctx and path_ctx.get(key) not in (None, ""):
            continue
        if isinstance(spec, dict):
            path_ctx[key] = _resolve_value(spec, path_ctx)
        else:
            path_ctx[key] = spec
    path_ctx.setdefault("startpoint", path_ctx.get("path_start", "inst/start/Q (CELL)"))
    path_ctx.setdefault("endpoint", path_ctx.get("path_end", "inst/end/D (CELL)"))
    path_ctx.setdefault("clock", path_ctx.get("common_pin", "pll_cpu_clk"))

    # 再解析 title 各属性（可能引用 path_vars / startpoint / endpoint）
    title_attrs = config.get("title", {}).get("attributes") or config.get("title_attributes") or []
    for attr in title_attrs:
        name = (attr.get("name") or attr.get("key") or "").strip().lower().replace(" ", "_")
        spec = attr.get("value") or attr.get("spec") or {}
        path_ctx[name] = _resolve_value(spec, path_ctx)
    path_ctx["path"] = path_ctx
    return path_ctx


def _expand_row_templates(templates: list[dict]) -> list[dict]:
    """将 [{ type: clock, count: 2 }, ...] 展开为 [ { type: clock }, { type: clock }, ... ]。"""
    out = []
    for t in templates:
        row_type = (t.get("type") or t.get("row_type") or "pin").strip()
        count = int(t.get("count", 1))
        for _ in range(count):
            out.append({"type": row_type})
    return out


def generate_report(config: dict, output_path: str, seed: int | None = None) -> None:
    """
    根据 config 字典生成完整 timing 报告并写入 output_path。
    config 结构见下方 _example_config 或 README。
    """
    format_name = (config.get("format") or "format2").strip().lower()
    num_paths = int(config.get("num_paths", 1))
    title_config = config.get("title", {}).get("attributes") or config.get("title_attributes") or []
    path_table = config.get("path_table") or config.get("table") or {}
    column_order = path_table.get("column_order") or path_table.get("columns_order") or []
    columns_config = path_table.get("columns") or path_table.get("attributes") or {}
    row_templates = path_table.get("row_templates") or path_table.get("rows") or []
    capture_templates = path_table.get("capture_row_templates") or path_table.get("capture_rows") or []
    separator = path_table.get("separator") or "-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-"
    col_widths = path_table.get("column_widths") or _default_column_widths(column_order, format_name)
    # 累加规则：format1/pt 中 Path = cumsum(Incr)，format2 中 Time = cumsum(Delay)
    cumulative_rules = path_table.get("cumulative_rules") or {}
    if not cumulative_rules and format_name in ("format1", "pt", "apr"):
        cumulative_rules = {"Path": "Incr"}
    elif not cumulative_rules and format_name == "format2":
        cumulative_rules = {"Time": "Delay"}

    if not column_order and format_name == "format2":
        column_order = ["Type", "Fanout", "Cap", "D-Trans", "Trans", "Derate", "x-coord", "y-coord", "D-Delay", "Delay", "Time", "Description"]

    launch_rows = _expand_row_templates(row_templates)
    capture_rows = _expand_row_templates(capture_templates) if capture_templates else []
    cumulative_targets = set(cumulative_rules.keys())
    cumulative_sources = set(cumulative_rules.values())

    lines = []
    for path_idx in range(num_paths):
        path_meta = _generate_path_meta(config, path_idx, seed=(seed + path_idx) if seed is not None else None, launch_rows=launch_rows, capture_rows=capture_rows)
        launch_pts = path_meta.get("launch_points") or []
        capture_pts = path_meta.get("capture_points") or []
        # Title 块
        lines.append(_render_title_block(title_config, path_meta, format_name))
        lines.append("")
        # 表头
        if column_order:
            header = _render_table_row(
                column_order,
                {c: {"value": {"type": "fixed", "value": c}} for c in column_order},
                {"row_type": ""},
                format_name,
                col_widths,
            )
            lines.append(header)
            sep_line = "-" * max(len(header), 80)
            lines.append(sep_line)
        # Launch 段（累加：Path = cumsum(Incr) 或 Time = cumsum(Delay)）
        running_cumulative: dict[str, float] = {t: 0.0 for t in cumulative_rules}
        for i, row_tmpl in enumerate(launch_rows):
            row_type = row_tmpl.get("type", "pin")
            point_name = launch_pts[i] if i < len(launch_pts) else ""
            row_ctx = {
                "path": path_meta,
                "path_id": path_meta.get("path_id"),
                "path_index": path_idx,
                "row_type": row_type,
                "row_index": i,
                "point": point_name,
                "point_name": point_name,
            }
            row_ctx.update(path_meta)
            for target_col, source_col in cumulative_rules.items():
                src_cfg = columns_config.get(source_col) or {}
                when = src_cfg.get("when_type") or src_cfg.get("when")
                if when and row_type not in when:
                    continue
                incr_val = _resolve_value(src_cfg.get("value") or src_cfg.get("spec") or {}, {**row_ctx, "row": row_ctx})
                running_cumulative[target_col] += _to_float(incr_val)
                row_ctx[target_col] = round(running_cumulative[target_col], 3)
                row_ctx[source_col] = incr_val  # 显示与累加一致
            line = _render_table_row(column_order, columns_config, row_ctx, format_name, col_widths, cumulative_targets, cumulative_sources)
            if line.strip():
                lines.append(line)
        if separator:
            lines.append(separator)
        # Capture 段（独立累加）
        running_cumulative = {t: 0.0 for t in cumulative_rules}
        for i, row_tmpl in enumerate(capture_rows):
            row_type = row_tmpl.get("type", "clock")
            point_name = capture_pts[i] if i < len(capture_pts) else ""
            row_ctx = {
                "path": path_meta,
                "path_id": path_meta.get("path_id"),
                "path_index": path_idx,
                "row_type": row_type,
                "row_index": len(launch_rows) + i,
                "point": point_name,
                "point_name": point_name,
            }
            row_ctx.update(path_meta)
            for target_col, source_col in cumulative_rules.items():
                src_cfg = columns_config.get(source_col) or {}
                when = src_cfg.get("when_type") or src_cfg.get("when")
                if when and row_type not in when:
                    continue
                incr_val = _resolve_value(src_cfg.get("value") or src_cfg.get("spec") or {}, {**row_ctx, "row": row_ctx})
                running_cumulative[target_col] += _to_float(incr_val)
                row_ctx[target_col] = round(running_cumulative[target_col], 3)
                row_ctx[source_col] = incr_val  # 显示与累加一致
            line = _render_table_row(column_order, columns_config, row_ctx, format_name, col_widths, cumulative_targets, cumulative_sources)
            if line.strip():
                lines.append(line)
        if separator and capture_rows:
            lines.append(separator)
        # Slack 行（可选）
        if path_table.get("slack_line", True):
            slack_ctx = {"path": path_meta, "row_type": "slack", **path_meta}
            slack_line = _render_table_row(column_order, columns_config, slack_ctx, format_name, col_widths, cumulative_targets, cumulative_sources)
            if slack_line.strip():
                lines.append(slack_line)
        lines.append("")
        lines.append("")

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")


def load_config(yaml_path: str) -> dict:
    """加载 YAML 配置文件。"""
    if yaml is None:
        raise RuntimeError("请安装 PyYAML: pip install pyyaml")
    path = Path(yaml_path)
    if not path.is_file():
        raise FileNotFoundError(f"配置文件不存在: {yaml_path}")
    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(text) or {}


def run_gen_report(args) -> int:
    """CLI 入口：从 YAML 生成 timing 报告。"""
    if yaml is None:
        print("Error: 需要 PyYAML。请执行: pip install pyyaml", file=sys.stderr)
        return 1
    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: 解析 YAML 失败: {e}", file=sys.stderr)
        return 1
    output = getattr(args, "output", None)
    seed = getattr(args, "seed", None)
    try:
        if not output:
            fmt = str((config.get("format") or "unknown")).strip().lower()
            output = f"output/gen_{fmt}_timing_report.rpt"
        generate_report(config, output, seed=seed)
    except Exception as e:
        print(f"Error: 生成报告失败: {e}", file=sys.stderr)
        return 1
    print(f"Generated timing report -> {output}")
    return 0
