from __future__ import annotations

from .base import TimingReportTemplate


class PtReport(TimingReportTemplate):
    format_name = "pt"

    def title_line(self, name: str, value: str) -> str:
        return f"  {name}: {value}"

    def default_column_widths(self, column_order: list[str]) -> dict[str, int]:
        defaults = {
            "Point": 44,
            "Fanout": 12,
            "Cap": 8,
            "Trans": 8,
            "Derate": 10,
            "Incr": 10,
            "Path": 10,
        }
        return {c: defaults.get(c, 16) for c in column_order}

    def default_cumulative_rules(self) -> dict[str, str]:
        return {"Path": "Incr"}

