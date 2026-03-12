from __future__ import annotations

import csv
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ParseOutput:
    """解析结果容器。launch 按 common pin（startpoint）拆分为 launch_clock 与 data_path。"""

    launch_rows: list[dict[str, Any]]
    capture_rows: list[dict[str, Any]]
    summary_rows: list[dict[str, Any]]
    launch_clock_rows: list[dict[str, Any]]
    data_path_rows: list[dict[str, Any]]


class TimeParser(ABC):
    """Timing report 解析抽象基类（模板方法）。"""

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
        return [
            "path_id",
            "startpoint",
            "endpoint",
            "arrival_time",
            "required_time",
            "slack",
            "launch_clock_point_count",
            "data_path_point_count",
            "capture_point_count",
            "launch_clock_delay",
            "data_path_delay",
        ]

    @staticmethod
    def _normalize_pin(pin: str) -> str:
        if not pin:
            return ""
        s = pin.strip()
        if s.endswith("<-"):
            s = s[:-2].strip()
        if " (" in s:
            s = s.split(" (", 1)[0].strip()
        return s

    @staticmethod
    def _clean_metric_float(v: float, ndigits: int = 6) -> float:
        # 消除浮点累计噪声，避免 CSV 中出现 0.39000000000000001 这类显示
        return round(float(v), ndigits)

    @classmethod
    def split_launch_by_common_pin(
        cls,
        launch_rows: list[dict[str, Any]],
        startpoint: str,
        delay_attr: str = "Incr",
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int, int, float, float]:
        target = cls._normalize_pin(startpoint)
        launch_clock: list[dict[str, Any]] = []
        data_path: list[dict[str, Any]] = []
        found = False
        output_pin_suffixes = ("/Q", "/Z", "/ZN", "/ZP", "/QN", "/QB")
        for row in launch_rows:
            pt = (row.get("point") or "").strip()
            norm_pt = cls._normalize_pin(pt)
            # 兼容 PT 原始报告：Startpoint 可能是实例名（如 u_logic/Uu73z4_reg），
            # 而 launch 点是具体 pin（如 u_logic/Uu73z4_reg/Q）。
            is_target_row = (
                norm_pt == target
                or (target and norm_pt.startswith(target + "/"))
            )
            is_startpoint_output = is_target_row and any(norm_pt.endswith(suf) for suf in output_pin_suffixes)
            if not found and (norm_pt == target or is_startpoint_output):
                found = True
                # startpoint 所在行应归入 data_path（而不是 launch_clock）
                row["path_type"] = "data_path"
                data_path.append(row)
                continue
            if not found:
                row["path_type"] = "launch_clock"
                launch_clock.append(row)
            else:
                row["path_type"] = "data_path"
                data_path.append(row)

        def _sum_delay(rows: list[dict[str, Any]]) -> float:
            total = 0.0
            for r in rows:
                val = r.get(delay_attr)
                if val is None:
                    continue
                try:
                    s = str(val).strip()
                    m = re.search(r"-?\d+(?:\.\d+)?", s)
                    if not m:
                        continue
                    total += float(m.group(0))
                except (ValueError, TypeError):
                    pass
            return total

        lc_delay = _sum_delay(launch_clock)
        dp_delay = _sum_delay(data_path)
        return launch_clock, data_path, len(launch_clock), len(data_path), lc_delay, dp_delay

    def parse_report(self, report_path: str) -> ParseOutput:
        blocks = self.scan_path_blocks(report_path)
        launch_rows: list[dict[str, Any]] = []
        capture_rows: list[dict[str, Any]] = []
        launch_clock_rows: list[dict[str, Any]] = []
        data_path_rows: list[dict[str, Any]] = []
        summary_rows: list[dict[str, Any]] = []
        delay_attr = "Incr" if "Incr" in self.attrs_order else "Delay"

        for path_id, path_text in blocks:
            meta, launch, capture = self.parse_one_path(path_id, path_text)
            lc, dp, lc_n, dp_n, lc_delay, dp_delay = self.split_launch_by_common_pin(
                launch, meta.get("startpoint", ""), delay_attr=delay_attr
            )
            meta["launch_clock_point_count"] = lc_n
            meta["data_path_point_count"] = dp_n
            meta["capture_point_count"] = len(capture)
            meta["launch_clock_delay"] = self._clean_metric_float(lc_delay)
            meta["data_path_delay"] = self._clean_metric_float(dp_delay)
            summary_rows.append(meta)
            launch_rows.extend(launch)
            launch_clock_rows.extend(lc)
            data_path_rows.extend(dp)
            capture_rows.extend(capture)

        return ParseOutput(
            launch_rows,
            capture_rows,
            summary_rows,
            launch_clock_rows,
            data_path_rows,
        )

    @abstractmethod
    def scan_path_blocks(self, report_path: str) -> list[tuple[int, str]]:
        ...

    @abstractmethod
    def parse_one_path(
        self, path_id: int, path_text: str
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
        ...

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

