from __future__ import annotations

import re
from typing import Any

from .base import TimingReportTemplate, ValueResolver, _str_value


class Format1Report(TimingReportTemplate):
    format_name = "format1"

    def float_decimals(self) -> int:
        return 4

    def title_line(self, name: str, value: str) -> str:
        return f"  {name}: {value}"

    def default_column_widths(self, column_order: list[str]) -> dict[str, int]:
        defaults = {
            "Point": 140,
            "Fanout": 8,
            "Derate": 10,
            "Cap": 12,
            "Trans": 12,
            "Location": 26,
            "Incr": 10,
            "Path": 10,
        }
        return {c: defaults.get(c, 16) for c in column_order}

    def default_cumulative_rules(self) -> dict[str, str]:
        return {"Path": "Incr"}

    def separator_after_launch(self) -> bool:
        # 参考 format1 样例：launch 与 capture 之间不加分隔线
        return False

    def separator_before_capture_row(self, row_type: str) -> bool:
        # 参考样例：capture 中在 required 前与 slack 前增加分隔线
        return row_type in ("required", "slack")

    def blank_line_between_segments(self) -> bool:
        # launch 和 capture 中间保留一个空行
        return True

    def render_row(self, plan, row_ctx: dict[str, Any], cumulative_targets: set[str], cumulative_sources: set[str]) -> str:
        def _normalize_float_text(text: str) -> str:
            return re.sub(
                r"-?\d+\.\d+",
                lambda m: f"{float(m.group(0)):.4f}",
                text or "",
            )

        rt = str(row_ctx.get("row_type", "")).strip().lower()
        # format1: Path 后追加 r/f 仅作用于 input/output pin 行
        if rt in ("input_pin", "output_pin"):
            path_val = row_ctx.get("Path")
            if path_val not in (None, ""):
                try:
                    v = float(str(path_val).strip())
                    row_ctx["Path"] = f"{v:.4f} {row_ctx.get('edge', 'r')}"
                except (TypeError, ValueError):
                    pass

        # format1: port 行仅保留单个 Location 符号 "-"，其余属性按配置生成
        cells: list[str] = []
        for col in plan.column_order:
            cfg = plan.columns_config.get(col) or {}
            when = cfg.get("when_type") or cfg.get("when")
            row_type = row_ctx.get("row_type", "")
            if when and row_type and row_type not in when:
                cells.append("")
                continue
            if col == "Location" and rt == "port":
                cells.append("-")
                continue
            if col in cumulative_targets and col in row_ctx:
                cells.append(_str_value(row_ctx[col], self.float_decimals()))
                continue
            if col in cumulative_sources and col in row_ctx:
                cells.append(_str_value(row_ctx[col], self.float_decimals()))
                continue
            spec = cfg.get("value") or cfg.get("spec") or {}
            val = ValueResolver.resolve_value(spec, {**row_ctx, "row": row_ctx, "path": row_ctx.get("path") or {}})
            cells.append(_normalize_float_text(_str_value(val, self.float_decimals())))

        parts: list[str] = []
        for i, col in enumerate(plan.column_order):
            w = int(plan.col_widths.get(col, 16))
            parts.append((cells[i] if i < len(cells) else "").ljust(w)[:w])
        return "".join(parts).rstrip()

