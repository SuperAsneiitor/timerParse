from __future__ import annotations

from typing import Any

from .base import TimingReportTemplate


class Format1Report(TimingReportTemplate):
    format_name = "format1"

    def title_line(self, name: str, value: str) -> str:
        return f"  {name}: {value}"

    def default_column_widths(self, column_order: list[str]) -> dict[str, int]:
        defaults = {
            "Point": 140,
            "Fanout": 8,
            "Cap": 12,
            "Trans": 12,
            "Location": 18,
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
        # format1: Path 后追加 r/f 仅作用于 input/output pin 行
        rt = str(row_ctx.get("row_type", "")).strip().lower()
        if rt in ("input_pin", "output_pin"):
            path_val = row_ctx.get("Path")
            if path_val not in (None, ""):
                try:
                    v = float(str(path_val).strip())
                    row_ctx["Path"] = f"{v:.3f} {row_ctx.get('edge', 'r')}"
                except (TypeError, ValueError):
                    pass
        return super().render_row(plan, row_ctx, cumulative_targets, cumulative_sources)

