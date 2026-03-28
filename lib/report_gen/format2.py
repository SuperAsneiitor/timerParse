from __future__ import annotations

import re
from typing import Any

from .base import TimingReportTemplate, ValueResolver, _str_value


class Format2Report(TimingReportTemplate):
    format_name = "format2"

    def float_decimals(self) -> int:
        return 4

    def title_line(self, name: str, value: str) -> str:
        name_width = 24
        return f"  {name:<{name_width}}  :  {value}"

    def default_column_widths(self, column_order: list[str]) -> dict[str, int]:
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

    def default_cumulative_rules(self) -> dict[str, str]:
        return {"Time": "Delay"}

    def separator_before_capture_row(self, row_type: str) -> bool:
        # capture: constraint -> required_path(紧跟) -> 分隔线 -> required/arrival -> 分隔线 -> slack
        return row_type in ("required", "slack")

    def separator_after_launch(self) -> bool:
        # launch 与 capture 之间使用空行分隔
        return False

    def blank_line_between_segments(self) -> bool:
        return True

    def separator_after_capture(self) -> bool:
        # slack 后不再加 -=- 分隔线，用空行和下一组 path 分隔
        return False

    def render_row(self, plan, row_ctx: dict[str, Any], cumulative_targets: set[str], cumulative_sources: set[str]) -> str:
        def _normalize_float_text(text: str) -> str:
            return re.sub(
                r"-?\d+\.\d+",
                lambda m: f"{float(m.group(0)):.4f}",
                text or "",
            )

        # format2: pin/port 行在 Time 与 Description 之间使用上升/下降沿符号（/ 或 \）
        rt = str(row_ctx.get("row_type", "")).strip().lower()
        point = str(row_ctx.get("point", "") or "").strip()
        if rt in ("clock_net_delay", "clock_reconv", "clock_uncertainty"):
            row_ctx["display_type"] = "clock"
        if rt == "required_path":
            row_ctx["display_type"] = "required"
        if rt in ("input_pin", "output_pin", "pin", "port"):
            row_ctx["description_text"] = f"{row_ctx.get('edge_symbol', '/')} {point}"
        else:
            row_ctx["description_text"] = point

        cells: list[str] = []
        for col in plan.column_order:
            cfg = plan.columns_config.get(col) or {}
            when = cfg.get("when_type") or cfg.get("when")
            row_type = row_ctx.get("row_type", "")
            if when and row_type and row_type not in when:
                cells.append("")
                continue

            if col in cumulative_targets and col in row_ctx:
                val = row_ctx[col]
            elif col in cumulative_sources and col in row_ctx:
                val = row_ctx[col]
            else:
                spec = cfg.get("value") or cfg.get("spec") or {}
                val = ValueResolver.resolve_value(spec, {**row_ctx, "row": row_ctx, "path": row_ctx.get("path") or {}})

            text = _normalize_float_text(_str_value(val, self.float_decimals()))
            # 不在代码里硬编码单位；Cap 保持纯数值，单位变更通过配置/词法层处理。
            if col == "x-coord" and text:
                text = "{  " + text
            elif col == "y-coord" and text:
                text = text + "}"
            cells.append(text)

        parts: list[str] = []
        for i, col in enumerate(plan.column_order):
            w = int(plan.col_widths.get(col, 16))
            parts.append((cells[i] if i < len(cells) else "").ljust(w)[:w])
        return "".join(parts).rstrip()

