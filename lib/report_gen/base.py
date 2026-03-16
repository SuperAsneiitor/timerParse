from __future__ import annotations

import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]


def _to_float(v: Any) -> float:
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip())
    except (ValueError, TypeError):
        return 0.0


def _str_value(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:.3f}" if abs(v) < 1e6 else str(v)
    return "" if v is None else str(v)


class ValueResolver:
    """YAML value 解析：fixed/enum/random/format/ref 等。"""

    @staticmethod
    def resolve_value(spec: Any, ctx: dict[str, Any]) -> Any:
        if not isinstance(spec, dict):
            return spec
        kind = (spec.get("type") or spec.get("kind") or "fixed").strip().lower()
        if kind == "fixed":
            return spec.get("value", "")
        if kind == "enum":
            choices = spec.get("choices") or spec.get("options") or []
            if not choices:
                return ""
            weights = spec.get("weights")
            if weights and len(weights) == len(choices):
                return random.choices(choices, weights=weights, k=1)[0]
            return random.choice(choices)
        if kind == "random_float":
            lo = float(spec.get("min", 0))
            hi = float(spec.get("max", 1))
            decimals = int(spec.get("decimals", 3))
            return round(random.uniform(lo, hi), decimals)
        if kind == "random_int":
            lo = int(spec.get("min", 0))
            hi = int(spec.get("max", 10))
            return random.randint(lo, hi)
        if kind == "random_coord":
            x_lo = float(spec.get("x_min", 0))
            x_hi = float(spec.get("x_max", 100))
            y_lo = float(spec.get("y_min", 0))
            y_hi = float(spec.get("y_max", 100))
            decimals = int(spec.get("decimals", 2))
            x = round(random.uniform(x_lo, x_hi), decimals)
            y = round(random.uniform(y_lo, y_hi), decimals)
            return f"({x:.{decimals}f}, {y:.{decimals}f})"
        if kind in ("format", "template"):
            tpl = spec.get("template") or spec.get("format") or spec.get("value") or ""
            return ValueResolver.format_template(str(tpl), ctx)
        if kind == "ref":
            key = spec.get("ref") or spec.get("field")
            return ctx.get(str(key), "")
        if kind == "row_type":
            return ctx.get("row_type", "")
        if kind == "sequence":
            start = int(spec.get("start", 1))
            step = int(spec.get("step", 1))
            idx = int(ctx.get("path_index", 0))
            return start + idx * step
        return spec.get("value", "")

    @staticmethod
    def format_template(tpl: str, ctx: dict[str, Any]) -> str:
        if not tpl:
            return ""
        text = tpl
        path = ctx.get("path") or {}
        row = ctx.get("row") or {}
        for k, v in path.items():
            text = text.replace("{" + f"path.{k}" + "}", str(v))
        for k, v in row.items():
            text = text.replace("{" + f"row.{k}" + "}", str(v))
        # 直接键 + 兜底替换
        for k, v in ctx.items():
            if k in ("path", "row"):
                continue
            token = "{" + k + "}"
            if token in text and v is not None and isinstance(v, (str, int, float, bool)):
                text = text.replace(token, str(v))
        return text


@dataclass
class RenderPlan:
    column_order: list[str]
    columns_config: dict[str, dict]
    row_templates: list[dict]
    capture_templates: list[dict]
    separator: str
    col_widths: dict[str, int]
    cumulative_rules: dict[str, str]


class TimingReportTemplate:
    """模板基类：提供公共生成流程；子类覆盖少量格式差异（title 行格式、默认累加规则等）。"""

    format_name: str = "unknown"

    def load_config(self, yaml_path: str) -> dict:
        if yaml is None:
            raise RuntimeError("请安装 PyYAML: pip install pyyaml")
        text = Path(yaml_path).read_text(encoding="utf-8")
        return yaml.safe_load(text) or {}

    def title_line(self, name: str, value: str) -> str:
        """子类可覆盖：title 行排版。"""
        return f"  {name}: {value}"

    def build_render_plan(self, config: dict) -> RenderPlan:
        path_table = config.get("path_table") or {}
        column_order = path_table.get("column_order") or []
        columns_config = path_table.get("columns") or {}
        row_templates = path_table.get("row_templates") or []
        capture_templates = path_table.get("capture_row_templates") or []
        separator = path_table.get("separator") or ""
        col_widths = path_table.get("column_widths") or self.default_column_widths(column_order)
        cumulative_rules = path_table.get("cumulative_rules") or self.default_cumulative_rules()
        return RenderPlan(
            column_order=column_order,
            columns_config=columns_config,
            row_templates=row_templates,
            capture_templates=capture_templates,
            separator=separator,
            col_widths=col_widths,
            cumulative_rules=cumulative_rules,
        )

    def default_column_widths(self, column_order: list[str]) -> dict[str, int]:
        return {c: 16 for c in column_order}

    def default_cumulative_rules(self) -> dict[str, str]:
        # 子类覆盖
        return {}

    def separator_after_launch(self) -> bool:
        return True

    def separator_before_capture_row(self, row_type: str) -> bool:
        return False

    def blank_line_between_segments(self) -> bool:
        return False

    def separator_after_capture(self) -> bool:
        return True

    def _expand_rows(self, templates: list[dict], ctx: dict[str, Any] | None = None) -> list[dict]:
        out: list[dict] = []
        local_ctx = ctx or {}
        for t in templates:
            # 支持 timing group 循环语义：
            # - { group: [input_pin, output_pin, net], repeat: N }
            # - repeat 可为固定值或 {type: ref/random_int/...}
            group = t.get("group") or t.get("group_types")
            if group:
                if isinstance(group, str):
                    group_types = [x.strip() for x in group.split(",") if x.strip()]
                elif isinstance(group, list):
                    group_types = [str(x).strip() for x in group if str(x).strip()]
                else:
                    group_types = []
                repeat_spec = t.get("repeat", t.get("count", 1))
                repeat_val = ValueResolver.resolve_value(repeat_spec, local_ctx)
                try:
                    repeat = int(repeat_val)
                except (TypeError, ValueError):
                    repeat = 1
                if repeat < 0:
                    repeat = 0
                for _ in range(repeat):
                    for gt in group_types:
                        out.append({"type": gt})
                continue

            row_type = (t.get("type") or t.get("row_type") or "pin").strip()
            count_spec = t.get("count", 1)
            count_val = ValueResolver.resolve_value(count_spec, local_ctx)
            try:
                count = int(count_val)
            except (TypeError, ValueError):
                count = 1
            if count < 0:
                count = 0
            for _ in range(count):
                out.append({"type": row_type})
        return out

    def _generate_segment_points(self, segment_rows: list[dict], segment_name: str, path_ctx: dict[str, Any], point_gen: dict[str, Any]) -> list[str]:
        pin_like_types = {"pin", "input_pin", "output_pin"}
        pin_count = sum(1 for r in segment_rows if (r.get("type") or "").strip().lower() in pin_like_types)
        out: list[str] = []
        pin_index = net_index = clock_index = point_index = 0
        io_instance_index = 0
        pending_input_instance: int | None = None
        input_pin_names = ["I", "A1", "A2", "D", "CK"]
        output_pin_names = ["Q", "Z", "ZN"]
        cell_types = [
            "CLKINV1_96S6T16L",
            "MUX2NV1C_96S6T16UL",
            "NOR2V1_96S6T16UL",
            "DSNQV2S_96S6T16UL",
        ]
        for row_tmpl in segment_rows:
            row_type = (row_tmpl.get("type") or "pin").strip().lower()
            ctx = {**path_ctx, "path": path_ctx, "row_type": row_type, "point_index": point_index, "segment": segment_name}
            if row_type in pin_like_types:
                logical_pin_index = pin_index
                ctx["pin_order_index"] = logical_pin_index
                ctx["is_startpoint"] = segment_name == "launch" and pin_index == 0
                ctx["is_endpoint"] = segment_name == "launch" and pin_index == pin_count - 1
                # input/output 成对时共享同一个实例索引（U号）和 cell_type，只变 pin 名
                if row_type == "input_pin":
                    instance_index = io_instance_index
                    pending_input_instance = instance_index
                    io_instance_index += 1
                elif row_type == "output_pin":
                    if pending_input_instance is not None:
                        instance_index = pending_input_instance
                        pending_input_instance = None
                    else:
                        instance_index = io_instance_index
                        io_instance_index += 1
                else:
                    instance_index = logical_pin_index
                    pending_input_instance = None
                ctx["pin_index"] = instance_index
                if row_type == "input_pin":
                    if ctx["is_startpoint"]:
                        pin_name = "CK"
                    elif ctx["is_endpoint"]:
                        pin_name = "D"
                    else:
                        pin_name = input_pin_names[logical_pin_index % len(input_pin_names)]
                elif row_type == "output_pin":
                    pin_name = output_pin_names[logical_pin_index % len(output_pin_names)]
                else:
                    pin_name = "Q" if ctx["is_startpoint"] else ("D" if ctx["is_endpoint"] else "Z")
                ctx["pin_name"] = pin_name
                ctx["pin_suffix"] = pin_name
                ctx["cell_type"] = cell_types[instance_index % len(cell_types)]
                pin_index += 1
            elif row_type == "net":
                ctx["net_index"] = net_index
                net_index += 1
            elif row_type in ("clock", "port"):
                ctx["clock_index"] = clock_index
                clock_index += 1
            point_index += 1

            gen = point_gen.get(row_type) or point_gen.get("default") or {}
            if isinstance(gen, dict) and "template" in gen:
                out.append(ValueResolver.format_template(str(gen["template"]), ctx))
            elif isinstance(gen, dict) and "value" in gen:
                out.append(_str_value(ValueResolver.resolve_value(gen["value"], ctx)))
            elif isinstance(gen, str):
                out.append(ValueResolver.format_template(gen, ctx))
            else:
                out.append("")
        return out

    def _build_path_ctx(self, config: dict, path_index: int, seed: int | None, launch_rows: list[dict], capture_rows: list[dict]) -> dict[str, Any]:
        if seed is not None:
            random.seed(seed)
        ctx: dict[str, Any] = {"path_index": path_index, "path_id": path_index + 1}
        # path_vars
        for k, spec in (config.get("path_vars") or {}).items():
            ctx[k] = ValueResolver.resolve_value(spec, ctx)
        ctx.setdefault("clock", ctx.get("common_pin", ctx.get("clock", "")))

        point_gen = config.get("point_generator") or {}
        launch_points = self._generate_segment_points(launch_rows, "launch", ctx, point_gen) if point_gen else []
        ctx["launch_points"] = launch_points
        # start/end/common_pin from launch pin-like rows
        pin_like_types = {"pin", "input_pin", "output_pin"}
        pin_indices = [i for i, r in enumerate(launch_rows) if (r.get("type") or "").strip().lower() in pin_like_types]
        output_indices = [i for i, r in enumerate(launch_rows) if (r.get("type") or "").strip().lower() == "output_pin"]
        input_indices = [i for i, r in enumerate(launch_rows) if (r.get("type") or "").strip().lower() == "input_pin"]
        if pin_indices and launch_points:
            # 优先将 startpoint 设为 launch 段第一个 output_pin，更贴近 PT 报告语义（Q/Z/ZN 发起数据）
            start_idx = output_indices[0] if output_indices else pin_indices[0]
            # endpoint 优先取最后一个 input_pin（如 D），否则取最后一个 pin-like
            end_idx = input_indices[-1] if input_indices else pin_indices[-1]
            ctx["startpoint"] = launch_points[start_idx]
            ctx["endpoint"] = launch_points[end_idx]
            # 约定：将首个 pin 作为 launch/capture 的「last common pin」近似，
            # 以便 title 中的 Last common pin 在 capture 段中也能出现同名 point。
            ctx.setdefault("common_pin", launch_points[start_idx])
        else:
            ctx.setdefault("startpoint", "")
            ctx.setdefault("endpoint", "")
            ctx.setdefault("common_pin", "")
        # capture 段在已知 common_pin 等上下文后再生成，便于使用 {common_pin} 等占位符
        capture_points = self._generate_segment_points(capture_rows, "capture", ctx, point_gen) if point_gen else []
        ctx["capture_points"] = capture_points
        # title-derived vars (snake_case keys)
        for attr in (config.get("title", {}).get("attributes") or []):
            name = (attr.get("name") or "").strip().lower().replace(" ", "_")
            if name in ctx:
                continue
            spec = attr.get("value") or {}
            ctx[name] = ValueResolver.resolve_value(spec, ctx)
        ctx["path"] = ctx
        return ctx

    def render_title_block(self, title_config: list[dict], path_ctx: dict[str, Any]) -> str:
        lines: list[str] = []
        for attr in title_config:
            name = attr.get("name") or ""
            spec = attr.get("value") or {}
            val = ValueResolver.resolve_value(spec, {**path_ctx, "path": path_ctx})
            lines.append(self.title_line(str(name), _str_value(val)))
        return "\n".join(lines) + "\n"

    def render_row(self, plan: RenderPlan, row_ctx: dict[str, Any], cumulative_targets: set[str], cumulative_sources: set[str]) -> str:
        cells: list[str] = []
        for col in plan.column_order:
            cfg = plan.columns_config.get(col) or {}
            when = cfg.get("when_type") or cfg.get("when")
            row_type = row_ctx.get("row_type", "")
            if when and row_type and row_type not in when:
                cells.append("")
                continue
            if col in cumulative_targets and col in row_ctx:
                cells.append(_str_value(row_ctx[col]))
                continue
            if col in cumulative_sources and col in row_ctx:
                cells.append(_str_value(row_ctx[col]))
                continue
            spec = cfg.get("value") or cfg.get("spec") or {}
            val = ValueResolver.resolve_value(spec, {**row_ctx, "row": row_ctx, "path": row_ctx.get("path") or {}})
            cells.append(_str_value(val))
        # fixed width
        parts = []
        for i, col in enumerate(plan.column_order):
            w = int(plan.col_widths.get(col, 16))
            parts.append((cells[i] if i < len(cells) else "").ljust(w)[:w])
        return "".join(parts).rstrip()

    def generate(self, config: dict, output_path: str, seed: int | None = None) -> None:
        plan = self.build_render_plan(config)
        title_config = config.get("title", {}).get("attributes") or []
        num_paths = int(config.get("num_paths", 1))
        cumulative_targets = set(plan.cumulative_rules.keys())
        cumulative_sources = set(plan.cumulative_rules.values())

        lines: list[str] = []
        for path_idx in range(num_paths):
            template_ctx: dict[str, Any] = {"path_index": path_idx, "path_id": path_idx + 1}
            if seed is not None:
                random.seed(seed + path_idx)
            for k, spec in (config.get("path_vars") or {}).items():
                template_ctx[k] = ValueResolver.resolve_value(spec, template_ctx)

            launch_rows = self._expand_rows(plan.row_templates, template_ctx)
            capture_rows = self._expand_rows(plan.capture_templates, template_ctx) if plan.capture_templates else []
            path_ctx = self._build_path_ctx(config, path_idx, (seed + path_idx) if seed is not None else None, launch_rows, capture_rows)
            launch_pts = path_ctx.get("launch_points") or []
            capture_pts = path_ctx.get("capture_points") or []

            lines.append(self.render_title_block(title_config, path_ctx))
            lines.append("")

            if plan.column_order:
                header = "".join([c.ljust(int(plan.col_widths.get(c, 16)))[: int(plan.col_widths.get(c, 16))] for c in plan.column_order]).rstrip()
                lines.append(header)
                lines.append("-" * max(len(header), 80))

            running: dict[str, float] = {t: 0.0 for t in plan.cumulative_rules}
            edge = "r"
            output_seen = False
            launch_sep_added = False
            for i, row_tmpl in enumerate(launch_rows):
                row_type = row_tmpl.get("type", "pin")
                point_name = launch_pts[i] if i < len(launch_pts) else ""
                display_type = "pin" if str(row_type).strip().lower() in ("input_pin", "output_pin") else row_type
                rt = str(row_type).strip().lower()
                # format2: launch path 中在时钟 pin（第一个 input_pin）前加一行 -= 分隔符
                if rt == "input_pin" and not launch_sep_added and getattr(self, "format_name", "") == "format2" and plan.separator:
                    lines.append(plan.separator)
                    launch_sep_added = True
                if rt == "output_pin":
                    if output_seen:
                        edge = "f" if edge == "r" else "r"
                    else:
                        output_seen = True
                edge_symbol = "/" if edge == "r" else "\\"
                row_ctx = {
                    **path_ctx,
                    "path": path_ctx,
                    "row_type": row_type,
                    "display_type": display_type,
                    "row_index": i,
                    "point": point_name,
                    "edge": edge,
                    "edge_symbol": edge_symbol,
                }
                for target, source in plan.cumulative_rules.items():
                    src_cfg = plan.columns_config.get(source) or {}
                    when = src_cfg.get("when_type") or src_cfg.get("when")
                    if when and row_type not in when:
                        continue
                    incr_val = ValueResolver.resolve_value(src_cfg.get("value") or {}, {**row_ctx, "row": row_ctx})
                    if str(row_type).strip().lower() == "clock_uncertainty":
                        incr_val = -abs(_to_float(incr_val))
                    running[target] += _to_float(incr_val)
                    row_ctx[target] = round(running[target], 3)
                    row_ctx[source] = incr_val
                line = self.render_row(plan, row_ctx, cumulative_targets, cumulative_sources)
                if line.strip():
                    lines.append(line)

            launch_totals = {k: float(v) for k, v in running.items()}

            if plan.separator and self.separator_after_launch():
                lines.append(plan.separator)
            elif capture_rows and self.blank_line_between_segments():
                lines.append("")

            running = {t: 0.0 for t in plan.cumulative_rules}
            edge = "r"
            output_seen = False
            for i, row_tmpl in enumerate(capture_rows):
                row_type = row_tmpl.get("type", "clock")
                rt_for_sep = str(row_type).strip().lower()
                if plan.separator and self.separator_before_capture_row(rt_for_sep):
                    if not lines or lines[-1] != plan.separator:
                        lines.append(plan.separator)
                point_name = capture_pts[i] if i < len(capture_pts) else ""
                display_type = "pin" if str(row_type).strip().lower() in ("input_pin", "output_pin") else row_type
                rt = str(row_type).strip().lower()
                if rt == "output_pin":
                    if output_seen:
                        edge = "f" if edge == "r" else "r"
                    else:
                        output_seen = True
                edge_symbol = "/" if edge == "r" else "\\"
                row_ctx = {
                    **path_ctx,
                    "path": path_ctx,
                    "row_type": row_type,
                    "display_type": display_type,
                    "row_index": len(launch_rows) + i,
                    "point": point_name,
                    "edge": edge,
                    "edge_symbol": edge_symbol,
                }
                for target, source in plan.cumulative_rules.items():
                    src_cfg = plan.columns_config.get(source) or {}
                    when = src_cfg.get("when_type") or src_cfg.get("when")
                    if when and row_type not in when:
                        continue
                    incr_val = ValueResolver.resolve_value(src_cfg.get("value") or {}, {**row_ctx, "row": row_ctx})
                    if str(row_type).strip().lower() == "clock_uncertainty":
                        incr_val = -abs(_to_float(incr_val))
                    running[target] += _to_float(incr_val)
                    row_ctx[target] = round(running[target], 3)
                    row_ctx[source] = incr_val
                rt_norm = str(row_type).strip().lower()
                for target in plan.cumulative_rules.keys():
                    if rt_norm == "required":
                        row_ctx[target] = round(running.get(target, 0.0), 3)
                    elif rt_norm == "required_path":
                        row_ctx[target] = round(running.get(target, 0.0), 3)
                    elif rt_norm == "arrival":
                        row_ctx[target] = round(-launch_totals.get(target, 0.0), 3)
                    elif rt_norm == "slack":
                        row_ctx[target] = round(running.get(target, 0.0) - launch_totals.get(target, 0.0), 3)
                line = self.render_row(plan, row_ctx, cumulative_targets, cumulative_sources)
                if line.strip():
                    lines.append(line)

            if plan.separator and capture_rows and self.separator_after_capture():
                lines.append(plan.separator)

            lines.append("")
            lines.append("")

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(lines), encoding="utf-8")

