from __future__ import annotations

import re
from typing import Any

from .time_parser_base import TimeParser


class Format1Parser(TimeParser):
    """Format1(APR) 报告解析器。"""

    default_attrs_order = ["Fanout", "Cap", "Trans", "Location", "Incr", "Path"]
    skip_first_rows = 2
    default_attrs_by_type = {
        "net": ["Fanout"],
        "input_pin": ["Cap", "Trans", "Location", "Incr", "Path"],
        "output_pin": ["Cap", "Trans", "Location", "Incr", "Path"],
    }

    _output_pin_names = frozenset({"Q", "Z", "ZN", "ZP"})

    _re_startpoint = re.compile(r"^\s+Startpoint:\s+(.+?)\s+\(.+\)\s*$")
    _re_endpoint = re.compile(r"^\s+Endpoint:\s+(.+?)\s+\(.+\)\s*$")
    _re_clocked_by = re.compile(r"clocked by ([^\s)]+)")
    _re_slack = re.compile(r"^\s+slack\s+\((VIOLATED|MET)\)\s")
    _re_slack_value = re.compile(r"(-?\d+\.\d+)\s*$")
    _re_point_header = re.compile(r"^\s+Point\s+", re.IGNORECASE)
    _re_sep_line = re.compile(r"^\s+-{3,}\s*$")
    # 点表中 launch/capture 段通常从 "clock <clock_name> (rise|fall edge)" 开始。
    # 注意 clock 名不是固定 CPU_CLK，且可能存在 fall edge。
    _re_clock_edge = re.compile(r"^\s+clock\s+\S+\s+\((rise|fall)\s+edge\)\s", re.IGNORECASE)
    _re_data_arrival = re.compile(r"^\s+data\s+arrival\s+time\s")
    _re_library_setup = re.compile(r"^\s+library\s+setup\s+time\s")

    def scan_path_blocks(self, report_path: str) -> list[tuple[int, str]]:
        with open(report_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()

        blocks: list[tuple[int, str]] = []
        i = 0
        path_id = 0
        while i < len(lines):
            if self._re_startpoint.match(lines[i]):
                start_i = i
                path_id += 1
                i += 1
                while i < len(lines):
                    if self._re_startpoint.match(lines[i]):
                        break
                    if self._re_slack.match(lines[i]):
                        i += 1
                        break
                    i += 1
                blocks.append((path_id, "\n".join(lines[start_i:i])))
                continue
            i += 1
        return blocks

    def parse_one_path(
        self, path_id: int, path_text: str
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
        lines = path_text.splitlines()
        meta = {
            "path_id": path_id,
            "startpoint": "",
            "endpoint": "",
            "startpoint_clock": "",
            "endpoint_clock": "",
            "slack": "",
            "slack_status": "",
            "arrival_time": "",
            "required_time": "",
        }
        launch_rows: list[dict[str, Any]] = []
        capture_rows: list[dict[str, Any]] = []

        for line in lines:
            m = self._re_startpoint.match(line)
            if m:
                meta["startpoint"] = m.group(1).strip()
                cm = self._re_clocked_by.search(line)
                meta["startpoint_clock"] = cm.group(1).strip() if cm else ""
                continue
            m = self._re_endpoint.match(line)
            if m:
                meta["endpoint"] = m.group(1).strip()
                cm = self._re_clocked_by.search(line)
                meta["endpoint_clock"] = cm.group(1).strip() if cm else ""
                continue
            m = self._re_slack.match(line)
            if m:
                meta["slack_status"] = m.group(1).strip()
                vm = self._re_slack_value.search(line)
                meta["slack"] = vm.group(1).strip() if vm else ""
                break

        col_pos: dict[str, int] = {}
        table_start = 0
        for idx, line in enumerate(lines):
            if self._re_point_header.match(line):
                col_pos = self.extract_column_positions(line, self.attrs_order)
                if "Location" in col_pos:
                    table_start = idx + 1
                    if table_start < len(lines) and self._re_sep_line.match(lines[table_start]):
                        table_start += 1
                    break
                col_pos = {}

        in_launch = False
        launch_start_idx = -1
        for j in range(table_start, len(lines)):
            if self._re_clock_edge.match(lines[j]):
                in_launch = True
                launch_start_idx = j
                continue
            if in_launch and self._re_data_arrival.match(lines[j]):
                for k in range(launch_start_idx, j + 1):
                    point, attrs = self.parse_fixed_width_attrs(lines[k], col_pos, self.attrs_order)
                    if not point:
                        continue
                    filtered = self.apply_type_filter(attrs, self._infer_point_type(point), k - launch_start_idx)
                    launch_rows.append(self.build_point_row(meta, len(launch_rows) + 1, point, filtered))
                vm = re.search(r"(-?\d+\.\d+)\s*$", lines[j])
                if vm:
                    meta["arrival_time"] = vm.group(1).strip()
                break

        after_data_arrival = False
        in_capture = False
        capture_start_idx = -1
        for j in range(table_start, len(lines)):
            if self._re_data_arrival.match(lines[j]):
                after_data_arrival = True
                continue
            if after_data_arrival and self._re_clock_edge.match(lines[j]):
                in_capture = True
                capture_start_idx = j
                continue
            if in_capture and self._re_library_setup.match(lines[j]):
                for k in range(capture_start_idx, j):
                    point, attrs = self.parse_fixed_width_attrs(lines[k], col_pos, self.attrs_order)
                    if not point:
                        continue
                    filtered = self.apply_type_filter(attrs, self._infer_point_type(point), k - capture_start_idx)
                    capture_rows.append(self.build_point_row(meta, len(capture_rows) + 1, point, filtered))
                break

        for line in lines:
            if "data required time" in line:
                vm = re.search(r"(-?\d+\.\d+)\s*$", line)
                if vm:
                    meta["required_time"] = vm.group(1).strip()
                    break

        if not meta["arrival_time"]:
            for line in lines:
                if "data arrival time" in line:
                    vm = re.search(r"(-?\d+\.\d+)\s*$", line)
                    if vm:
                        meta["arrival_time"] = vm.group(1).strip()
                        break

        return meta, launch_rows, capture_rows

    def _infer_point_type(self, point_name: str) -> str:
        if not point_name or "(net)" in point_name:
            return "net"
        m = re.search(r"/([A-Za-z0-9_\[\]]+)\s*\(?[A-Z]?", point_name)
        pin = m.group(1) if m else ""
        if pin in self._output_pin_names:
            return "output_pin"
        return "input_pin"
