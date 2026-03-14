from __future__ import annotations

import random
from pathlib import Path

from .base import TimingReportTemplate, ValueResolver, _to_float, _str_value


class PtReport(TimingReportTemplate):
    format_name = "pt"

    @staticmethod
    def _strip_cell(point: str) -> tuple[str, str]:
        s = (point or "").strip()
        if " (" in s and s.endswith(")"):
            i = s.rfind(" (")
            return s[:i].strip(), s[i:].strip()
        return s, ""

    @classmethod
    def _instance_only(cls, point: str) -> str:
        base, _cell = cls._strip_cell(point)
        if "/" in base:
            return base.rsplit("/", 1)[0]
        return base

    @classmethod
    def _capture_ck_from_startpoint(cls, startpoint: str) -> str:
        base, cell = cls._strip_cell(startpoint)
        if "/" in base:
            inst = base.rsplit("/", 1)[0]
            return f"{inst}/CK{(' ' + cell) if cell else ''}".strip()
        return startpoint

    def render_title_block(self, title_config: list[dict], path_ctx: dict[str, object]) -> str:
        lines: list[str] = []
        clock = str(path_ctx.get("clock", "clk_hclk"))
        for attr in title_config:
            name = str(attr.get("name") or "")
            spec = attr.get("value") or {}
            val = _str_value(ValueResolver.resolve_value(spec, {**path_ctx, "path": path_ctx}))
            if name == "Startpoint":
                lines.append(f"  Startpoint: {self._instance_only(val)}")
                lines.append(f"              (rising edge-triggered flip-flop clocked by {clock})")
                continue
            if name == "Endpoint":
                lines.append(f"  Endpoint: {self._instance_only(val)}")
                lines.append(f"            (rising edge-triggered flip-flop clocked by {clock})")
                continue
            lines.append(f"  {name}: {val}")
        return "\n".join(lines) + "\n"

    def default_column_widths(self, column_order: list[str]) -> dict[str, int]:
        defaults = {
            "Point": 56,
            "Fanout": 12,
            "Cap": 8,
            "Trans": 8,
            "Derate": 10,
            "Mean": 10,
            "Sensit": 10,
            "Incr": 10,
            "Path": 10,
        }
        return {c: defaults.get(c, 16) for c in column_order}

    def default_cumulative_rules(self) -> dict[str, str]:
        return {"Path": "Incr"}

    def _render_fixed_row(self, plan, point_text: str, incr_text: str = "", path_text: str = "") -> str:
        cells = {c: "" for c in plan.column_order}
        if "Point" in cells:
            cells["Point"] = point_text
        if "Incr" in cells:
            cells["Incr"] = incr_text
        if "Path" in cells:
            cells["Path"] = path_text
        parts = []
        for col in plan.column_order:
            w = int(plan.col_widths.get(col, 16))
            parts.append(str(cells.get(col, "")).ljust(w)[:w])
        return "".join(parts).rstrip()

    @staticmethod
    def _format_with_edge(path_val: object, edge: str) -> str:
        v = _to_float(path_val)
        return f"{v:.2f} {edge}"

    @staticmethod
    def _format_incr(incr_val: object) -> str:
        v = _to_float(incr_val)
        return f"{v:.4f} &"

    def generate(self, config: dict, output_path: str, seed: int | None = None) -> None:
        # PT 采用专用流程，严格控制分隔符与 summary 区块位置。
        plan = self.build_render_plan(config)
        title_config = config.get("title", {}).get("attributes") or []
        num_paths = int(config.get("num_paths", 1))
        summary_policy = config.get("summary_policy") or {}
        stat_cfg = (summary_policy.get("statistical_adjustment") or {}) if isinstance(summary_policy, dict) else {}
        stat_enabled = bool(stat_cfg.get("enabled", True))
        stat_incr = str(stat_cfg.get("incr", "0.00"))
        stat_path = str(stat_cfg.get("path", "0.00"))
        cumulative_targets = set(plan.cumulative_rules.keys())
        cumulative_sources = set(plan.cumulative_rules.values())

        lines: list[str] = []
        for path_idx in range(num_paths):
            template_ctx: dict[str, object] = {"path_index": path_idx, "path_id": path_idx + 1}
            if seed is not None:
                random.seed(seed + path_idx)
            for k, spec in (config.get("path_vars") or {}).items():
                template_ctx[k] = ValueResolver.resolve_value(spec, template_ctx)

            launch_rows = self._expand_rows(plan.row_templates, template_ctx)
            capture_rows = self._expand_rows(plan.capture_templates, template_ctx) if plan.capture_templates else []
            path_ctx = self._build_path_ctx(
                config,
                path_idx,
                (seed + path_idx) if seed is not None else None,
                launch_rows,
                capture_rows,
            )
            path_ctx["startpoint_capture_ck"] = self._capture_ck_from_startpoint(str(path_ctx.get("startpoint", "")))
            launch_pts = path_ctx.get("launch_points") or []
            capture_pts = path_ctx.get("capture_points") or []

            lines.append(self.render_title_block(title_config, path_ctx))
            lines.append("")

            header = "".join(
                [c.ljust(int(plan.col_widths.get(c, 16)))[: int(plan.col_widths.get(c, 16))] for c in plan.column_order]
            ).rstrip()
            lines.append("  " + header)
            header_sep = "-" * max(len(header), 96)
            lines.append("  " + header_sep)

            launch_path_val = 0.0
            required_path_val = 0.0

            running = {t: 0.0 for t in plan.cumulative_rules}
            launch_edge = "r"
            launch_output_seen = False
            for i, row_tmpl in enumerate(launch_rows):
                row_type = row_tmpl.get("type", "pin")
                point_name = launch_pts[i] if i < len(launch_pts) else ""
                row_ctx = {**path_ctx, "path": path_ctx, "row_type": row_type, "row_index": i, "point": point_name}
                for target, source in plan.cumulative_rules.items():
                    src_cfg = plan.columns_config.get(source) or {}
                    when = src_cfg.get("when_type") or src_cfg.get("when")
                    if when and row_type not in when:
                        continue
                    incr_val = ValueResolver.resolve_value(src_cfg.get("value") or {}, {**row_ctx, "row": row_ctx})
                    if str(row_type).strip().lower() == "clock_uncertainty":
                        incr_val = -max(abs(_to_float(incr_val)), 0.0001)
                    running[target] += _to_float(incr_val)
                    row_ctx[target] = round(running[target], 4)
                    row_ctx[source] = incr_val

                rt = str(row_type).strip().lower()
                if rt in ("arrival",):
                    row_ctx["Path"] = round(running.get("Path", 0.0), 4)
                if rt in ("output_pin",):
                    if launch_output_seen:
                        launch_edge = "f" if launch_edge == "r" else "r"
                    else:
                        launch_output_seen = True
                if rt not in ("arrival", "required", "slack", "endpoint"):
                    if "Incr" in row_ctx:
                        if rt in ("input_pin", "output_pin", "pin"):
                            row_ctx["Incr"] = self._format_incr(row_ctx.get("Incr", 0.0))
                        else:
                            row_ctx["Incr"] = f"{_to_float(row_ctx.get('Incr', 0.0)):.2f}"
                    if "Path" in row_ctx and rt in ("input_pin", "output_pin", "pin", "net"):
                        row_ctx["Path"] = self._format_with_edge(row_ctx.get("Path", 0.0), launch_edge)

                line = self.render_row(plan, row_ctx, cumulative_targets, cumulative_sources)
                if line.strip():
                    lines.append("  " + line)
                if str(row_type).strip().lower() == "arrival":
                    launch_path_val = _to_float(row_ctx.get("Path", running.get("Path", 0.0)))

            # 对齐 raw PT：launch 与 capture 之间为空行，不加分隔线
            lines.append("")

            running = {t: 0.0 for t in plan.cumulative_rules}
            capture_edge = "r"
            capture_output_seen = False
            for i, row_tmpl in enumerate(capture_rows):
                row_type = row_tmpl.get("type", "clock")
                point_name = capture_pts[i] if i < len(capture_pts) else ""
                if str(row_type).strip().lower() == "endpoint":
                    point_name = self._capture_ck_from_startpoint(str(path_ctx.get("startpoint", "")))
                row_ctx = {**path_ctx, "path": path_ctx, "row_type": row_type, "row_index": len(launch_rows) + i, "point": point_name}
                for target, source in plan.cumulative_rules.items():
                    src_cfg = plan.columns_config.get(source) or {}
                    when = src_cfg.get("when_type") or src_cfg.get("when")
                    if when and row_type not in when:
                        continue
                    incr_val = ValueResolver.resolve_value(src_cfg.get("value") or {}, {**row_ctx, "row": row_ctx})
                    if str(row_type).strip().lower() == "clock_uncertainty":
                        incr_val = -max(abs(_to_float(incr_val)), 0.0001)
                    running[target] += _to_float(incr_val)
                    row_ctx[target] = round(running[target], 4)
                    row_ctx[source] = incr_val

                rt = str(row_type).strip().lower()
                if rt in ("required",):
                    row_ctx["Path"] = round(running.get("Path", 0.0), 4)
                if rt in ("output_pin",):
                    if capture_output_seen:
                        capture_edge = "f" if capture_edge == "r" else "r"
                    else:
                        capture_output_seen = True
                if rt not in ("arrival", "required", "slack", "endpoint"):
                    if "Incr" in row_ctx:
                        if rt in ("input_pin", "output_pin", "pin"):
                            row_ctx["Incr"] = self._format_incr(row_ctx.get("Incr", 0.0))
                        else:
                            row_ctx["Incr"] = f"{_to_float(row_ctx.get('Incr', 0.0)):.2f}"
                    if "Path" in row_ctx and rt in ("input_pin", "output_pin", "pin", "net", "endpoint"):
                        row_ctx["Path"] = self._format_with_edge(row_ctx.get("Path", 0.0), capture_edge)

                line = self.render_row(plan, row_ctx, cumulative_targets, cumulative_sources)
                if line.strip():
                    lines.append("  " + line)
                if str(row_type).strip().lower() == "required":
                    required_path_val = _to_float(row_ctx.get("Path", running.get("Path", 0.0)))

            # PT 固定 summary：分隔符 -> data required/data arrival -> 分隔符 -> statistical adjustment/slack
            if plan.separator:
                lines.append("  " + plan.separator)

            # 按用户模板：先 data arrival time，再 data required time
            lines.append("  " + self._render_fixed_row(plan, "data required time", "", f"{required_path_val:.2f}"))
            lines.append("  " + self._render_fixed_row(plan, "data arrival time", "", f"{-launch_path_val:.2f}"))

            if plan.separator:
                lines.append("  " + plan.separator)

            hold_slack = launch_path_val - required_path_val
            slack_status = "MET" if hold_slack >= 0 else "VIOLATED"
            # slack 前增加 statistical adjustment 行（可通过 summary_policy 开关）
            if stat_enabled:
                lines.append("  " + self._render_fixed_row(plan, "statistical adjustment", stat_incr, stat_path))
            lines.append("  " + self._render_fixed_row(plan, f"slack ({slack_status})", "", f"{hold_slack:.2f}"))

            lines.append("")
            lines.append("")

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(lines), encoding="utf-8")

