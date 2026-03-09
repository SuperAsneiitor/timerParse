from __future__ import annotations

import re
from typing import Any

from .time_parser_base import TimeParser


class Format2Parser(TimeParser):
    """Format2 报告解析器（Path Start/Path End 风格）。"""

    default_attrs_order = [
        "Type",
        "Fanout",
        "Cap",
        "D-Trans",
        "Trans",
        "Derate",
        "x-coord",
        "y-coord",
        "D-Delay",
        "Delay",
        "Time",
        "Description",
    ]
    skip_first_rows = 4
    default_attrs_by_type = {
        "net": ["Fanout", "Cap"],
        "input_pin": [
            "D-Trans",
            "Trans",
            "Derate",
            "x-coord",
            "y-coord",
            "D-Delay",
            "Delay",
            "Time",
            "Description",
        ],
        "output_pin": ["Trans", "Derate", "x-coord", "y-coord", "Delay", "Time", "Description"],
    }

    _output_pin_names = frozenset({"Q", "Z", "ZN", "ZP"})

    _re_path_start = re.compile(
        r"^\s*Path Start\s+:\s+(.+?)\s+\(\s*flip-flop[^)]*,\s*(\w+)\s*\)\s*$"
    )
    _re_path_end = re.compile(
        r"^\s*Path End\s+:\s+(.+?)\s+\(\s*flip-flop[^)]*,\s*(\w+)\s*\)\s*$"
    )
    _re_slack_value = re.compile(r"(-?\d+\.\d+)\s+slack\s+\(")
    _re_slack_status = re.compile(r"slack\s+\((\w+)\)")
    _re_sep = re.compile(r"^-=+\s*$")
    _re_data_arrival = re.compile(r"data arrival time")

    def scan_path_blocks(self, report_path: str) -> list[tuple[int, str]]:
        with open(report_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        blocks: list[tuple[int, str]] = []
        i = 0
        path_id = 0
        while i < len(lines):
            if self._re_path_start.match(lines[i]):
                start_i = i
                path_id += 1
                i += 1
                while i < len(lines):
                    if self._re_path_start.match(lines[i]):
                        break
                    if "slack (VIOLATED)" in lines[i] or "slack (MET)" in lines[i]:
                        i += 1
                        break
                    i += 1
                blocks.append((path_id, "".join(lines[start_i:i])))
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
            m = self._re_path_start.match(line)
            if m:
                meta["startpoint"] = m.group(1).strip()
                meta["startpoint_clock"] = m.group(2).strip()
                continue
            m = self._re_path_end.match(line)
            if m:
                meta["endpoint"] = m.group(1).strip()
                meta["endpoint_clock"] = m.group(2).strip()
                continue
            if "slack (VIOLATED)" in line or "slack (MET)" in line:
                vm = self._re_slack_value.search(line)
                sm = self._re_slack_status.search(line)
                if vm:
                    meta["slack"] = vm.group(1).strip()
                if sm:
                    meta["slack_status"] = sm.group(1).strip()
                break

        col_pos: dict[str, int] = {}
        table_start = 0
        for idx, line in enumerate(lines):
            if "Type" in line and "Fanout" in line and "Cap" in line:
                col_pos = self.extract_column_positions(line, self.attrs_order)
                if "Description" in col_pos:
                    table_start = idx + 1
                    if table_start < len(lines) and self._re_sep.match(lines[table_start]):
                        table_start += 1
                    break
                col_pos = {}

        in_launch = True
        in_capture = False
        for j in range(table_start, len(lines)):
            if self._re_sep.match(lines[j]):
                if in_capture:
                    break
                continue

            point, attrs, point_type = self._parse_format2_line(lines[j], col_pos)
            if not point:
                continue

            seg_idx = len(launch_rows) if in_launch else len(capture_rows)
            filtered = self.apply_type_filter(attrs, point_type, seg_idx)

            if self._re_data_arrival.search(lines[j]):
                if in_launch:
                    vm = re.search(r"(-?\d+\.\d+)\s+data arrival time", lines[j])
                    if vm:
                        meta["arrival_time"] = vm.group(1).strip()
                launch_rows.append(self.build_point_row(meta, len(launch_rows) + 1, point, filtered))
                in_launch = False
                in_capture = True
                continue

            if in_launch:
                launch_rows.append(self.build_point_row(meta, len(launch_rows) + 1, point, filtered))
            elif in_capture:
                capture_rows.append(self.build_point_row(meta, len(capture_rows) + 1, point, filtered))

        for line in lines:
            if "data required time" in line:
                vm = re.search(r"(-?\d+\.\d+)\s+data required time", line)
                if vm:
                    meta["required_time"] = vm.group(1).strip()
                    break

        return meta, launch_rows, capture_rows

    def _parse_format2_line(
        self,
        line: str,
        col_pos: dict[str, int],
    ) -> tuple[str, dict[str, str], str]:
        content = line.rstrip()
        if not content.strip() or "Description" not in col_pos:
            return "", {}, "other"

        ordered = sorted(
            [name for name in self.attrs_order if name in col_pos],
            key=lambda x: col_pos[x],
        )
        if not ordered:
            return "", {}, "other"

        desc_start = col_pos["Description"]
        point_raw = content[desc_start:].strip()
        if re.search(r"\s+/\s+", point_raw):
            point_raw = re.split(r"\s+/\s+", point_raw, maxsplit=1)[-1].strip()
        elif re.search(r"\s+\\\s+", point_raw):
            point_raw = re.split(r"\s+\\\s+", point_raw, maxsplit=1)[-1].strip()
        else:
            point_raw = re.sub(r"^[\s\d.-]+", "", point_raw).strip()
        point = point_raw.lstrip("/ \\").strip() if point_raw else ""

        attrs: dict[str, str] = {name: "" for name in self.attrs_order}
        type_col = ""
        for i, name in enumerate(ordered):
            start = col_pos[name]
            end = col_pos[ordered[i + 1]] if i + 1 < len(ordered) else len(content)
            value = content[start:end].strip() if start < end else ""
            value = "" if value in ("-", "-0.000") else value
            if name == "Type":
                type_col = value
            if name == "Description":
                attrs["Description"] = point
                continue
            if name in ("x-coord", "y-coord"):
                continue
            if name == "Derate":
                dm = re.search(r"(\d+\.\d+\s*,\s*\d+\.\d+)", content)
                attrs[name] = dm.group(1).replace(" ", "") if dm else value
                continue
            attrs[name] = value

        brace = re.search(r"\{\s*([-\d.]+)\s+([-\d.]+)\s*\}", content)
        if brace:
            attrs["x-coord"] = brace.group(1)
            attrs["y-coord"] = brace.group(2)
            rest = content[brace.end() :]
            m3 = re.match(r"\s*(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+", rest)
            if m3:
                attrs["D-Delay"] = m3.group(1)
                attrs["Delay"] = m3.group(2)
                attrs["Time"] = m3.group(3)
            else:
                m2 = re.match(r"\s*(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+", rest)
                if m2:
                    attrs["D-Delay"] = ""
                    attrs["Delay"] = m2.group(1)
                    attrs["Time"] = m2.group(2)

        return point, attrs, self._infer_point_type(type_col, point)

    def _infer_point_type(self, type_col: str, point_name: str) -> str:
        t = (type_col or "").strip().lower()
        if t == "net":
            return "net"
        if t == "pin":
            m = re.search(r"/([A-Za-z0-9_\[\]]+)\s*\(?[A-Z]?", point_name)
            pin = m.group(1) if m else ""
            if pin in self._output_pin_names:
                return "output_pin"
            return "input_pin"
        return "other"
