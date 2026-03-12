from __future__ import annotations

from .base import TimingReportTemplate


class Format2Report(TimingReportTemplate):
    format_name = "format2"

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

