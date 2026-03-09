from __future__ import annotations

import csv
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ParseOutput:
    """解析结果容器。"""

    launch_rows: list[dict[str, Any]]
    capture_rows: list[dict[str, Any]]
    summary_rows: list[dict[str, Any]]


class TimeParser(ABC):
    """
    Timing report 解析抽象基类（模板方法）。

    子类只需要实现：
    1) `scan_path_blocks`：如何切分 path；
    2) `parse_one_path`：如何解析单条 path。
    """

    default_attrs_order: list[str] = []
    skip_first_rows: int = 0
    default_attrs_by_type: dict[str, list[str]] = {}

    def __init__(
        self,
        attrs_order: list[str] | None = None,
        attrs_by_type: dict[str, list[str]] | None = None,
    ) -> None:
        self.attrs_order = attrs_order[:] if attrs_order else self.default_attrs_order[:]
        self.attrs_by_type = (
            {k: v[:] for k, v in attrs_by_type.items()}
            if attrs_by_type
            else {k: v[:] for k, v in self.default_attrs_by_type.items()}
        )

    @property
    def point_base_columns(self) -> list[str]:
        return [
            "path_id",
            "startpoint",
            "endpoint",
            "startpoint_clock",
            "endpoint_clock",
            "slack",
            "slack_status",
            "point_index",
            "point",
        ]

    @property
    def summary_columns(self) -> list[str]:
        return ["path_id", "startpoint", "endpoint", "arrival_time", "required_time", "slack"]

    def parse_report(self, report_path: str) -> ParseOutput:
        """模板流程：切分 -> 逐条解析 -> 汇总。"""
        blocks = self.scan_path_blocks(report_path)
        launch_rows: list[dict[str, Any]] = []
        capture_rows: list[dict[str, Any]] = []
        summary_rows: list[dict[str, Any]] = []

        for path_id, path_text in blocks:
            meta, launch, capture = self.parse_one_path(path_id, path_text)
            summary_rows.append(meta)
            launch_rows.extend(launch)
            capture_rows.extend(capture)

        return ParseOutput(launch_rows, capture_rows, summary_rows)

    @abstractmethod
    def scan_path_blocks(self, report_path: str) -> list[tuple[int, str]]:
        """扫描报告并切分 path block。"""

    @abstractmethod
    def parse_one_path(
        self, path_id: int, path_text: str
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
        """解析单条路径。"""

    def build_point_row(
        self,
        meta: dict[str, Any],
        point_index: int,
        point: str,
        attrs: dict[str, Any],
    ) -> dict[str, Any]:
        row = {
            "path_id": meta["path_id"],
            "startpoint": meta["startpoint"],
            "endpoint": meta["endpoint"],
            "startpoint_clock": meta["startpoint_clock"],
            "endpoint_clock": meta["endpoint_clock"],
            "slack": meta["slack"],
            "slack_status": meta["slack_status"],
            "point_index": point_index,
            "point": point,
        }
        for name in self.attrs_order:
            row[name] = attrs.get(name, "")
        return row

    def apply_type_filter(
        self,
        attrs: dict[str, Any],
        point_type: str,
        segment_row_index: int,
    ) -> dict[str, Any]:
        """按 point 类型过滤属性；前 N 行保留全属性。"""
        out = {name: attrs.get(name, "") for name in self.attrs_order}
        if segment_row_index < self.skip_first_rows:
            return out

        allowed = self.attrs_by_type.get(point_type)
        if not allowed:
            return out
        allowed_set = set(allowed)
        for name in self.attrs_order:
            if name not in allowed_set:
                out[name] = ""
        return out

    @staticmethod
    def extract_column_positions(header_line: str, attrs_order: list[str]) -> dict[str, int]:
        """从表头提取列起始位置。"""
        col_pos: dict[str, int] = {}
        for name in attrs_order:
            idx = header_line.find(" " + name + " ")
            if idx < 0:
                idx = header_line.find(name)
            if idx >= 0:
                col_pos[name] = idx
        return col_pos

    @staticmethod
    def parse_fixed_width_attrs(
        line: str,
        col_pos: dict[str, int],
        attrs_order: list[str],
    ) -> tuple[str, dict[str, str]]:
        """按固定列宽解析一行（适用 format1/pt）。"""
        content = line.rstrip()
        ordered = sorted(
            [name for name in attrs_order if name in col_pos],
            key=lambda x: col_pos[x],
        )
        if not ordered:
            return "", {}

        point = content[: col_pos[ordered[0]]].strip()
        attrs: dict[str, str] = {}
        for i, name in enumerate(ordered):
            start = col_pos[name]
            end = col_pos[ordered[i + 1]] if i + 1 < len(ordered) else len(content)
            value = content[start:end].strip() if start < end else ""
            attrs[name] = "" if value == "-" else value
        for name in attrs_order:
            attrs.setdefault(name, "")
        return point, attrs

    def write_csv(self, output_path: str, rows: list[dict[str, Any]], columns: list[str]) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
