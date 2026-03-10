from __future__ import annotations

import re
from typing import Any

from .time_parser_base import TimeParser


def _desc_to_point(desc: str) -> str:
    """从 Description 提取 point 名称：Time 与 Description 间可能为 / 或 \\，取其后部分。仅用 split，不用正则。"""
    if not desc:
        return ""
    s = desc.strip()
    if s.startswith("/ "):
        s = s[2:].strip()
    elif s.startswith("\\ "):
        s = s[2:].strip()
    if " / " in s:
        s = s.split(" / ", 1)[-1].strip()
    elif " \\ " in s:
        s = s.split(" \\ ", 1)[-1].strip()
    # 去掉首部的数字、小数点、空格
    while s and s[0] in " 0123456789.-":
        s = s[1:].lstrip()
    return s.strip()


def _pin_name_from_desc(desc: str) -> str:
    """从 Description 中取出 pin 名（路径最后一段，括号前）。用于区分 input_pin / output_pin。"""
    s = _desc_to_point(desc)
    if " (" in s:
        s = s.split(" (", 1)[0]
    if "/" in s:
        s = s.split("/")[-1]
    if "\\" in s:
        s = s.split("\\")[-1]
    return s.strip()


def _is_numeric_token(s: str) -> bool:
    """判断是否为数字 token（含负号、小数点），仅用字符串方法。"""
    s = s.strip()
    if not s:
        return False
    t = s.lstrip("-")
    return t.replace(".", "", 1).isdigit()


def _tail_n_numeric_and_desc(line: str, n: int) -> tuple[list[str], str]:
    """从整行用 split 解析：跳过第一个 token（Type），取最后 n 个数字 token，其后为 Description。返回 (数字列表, 描述)。"""
    tokens = line.split()
    if len(tokens) <= 1:
        return [], ""
    rest = tokens[1:]
    indices: list[int] = []
    for j in range(len(rest) - 1, -1, -1):
        if _is_numeric_token(rest[j]):
            indices.append(j)
            if len(indices) == n:
                break
    if len(indices) < n:
        return [], " ".join(rest)
    values = [rest[i] for i in sorted(indices)]
    last_idx = max(indices)
    desc = " ".join(rest[last_idx + 1 :])
    return values, desc


# 报告里 Type 为 pin 时，若 pin 名为下列之一则为 output_pin，否则为 input_pin
_OUTPUT_PIN_NAMES = frozenset({"Q", "Z", "ZN", "ZP"})


class Format2Parser(TimeParser):
    """Format2 报告解析器（Path Start/Path End 风格）。按 Type 分派到不同解析方法，使用 split/切片提取属性，不用正则匹配属性。"""

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
        "input_pin": [
            "Type",
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
        "output_pin": [
            "Type",
            "Trans",
            "Derate",
            "x-coord",
            "y-coord",
            "Delay",
            "Time",
            "Description",
        ],
        "net": ["Type", "Fanout", "Cap", "Description"],
        "clock": ["Type", "Delay", "Time", "Description"],
        "port": ["Type", "Trans", "x-coord", "y-coord", "Delay", "Time", "Description"],
        "constraint": ["Type", "Delay", "Time", "Description"],
        "required": ["Type", "Time", "Description"],
        "arrival": ["Type", "Time", "Description"],
        "slack": ["Type", "Time", "Description"],
    }

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

            point, attrs, point_type = self._parse_line_by_type(lines[j], col_pos, lines[j])
            if not point and point_type not in ("required", "arrival", "slack"):
                continue

            seg_idx = len(launch_rows) if in_launch else len(capture_rows)
            filtered = self.apply_type_filter(attrs, point_type, seg_idx)

            if self._re_data_arrival.search(lines[j]):
                if in_launch:
                    parts = lines[j].split("data arrival time", 1)
                    if len(parts) == 2:
                        tok = parts[0].strip().split()
                        if tok:
                            meta["arrival_time"] = tok[-1]
                launch_rows.append(
                    self.build_point_row(meta, len(launch_rows) + 1, point, filtered)
                )
                in_launch = False
                in_capture = True
                continue

            if in_launch:
                launch_rows.append(
                    self.build_point_row(meta, len(launch_rows) + 1, point, filtered)
                )
            elif in_capture:
                capture_rows.append(
                    self.build_point_row(meta, len(capture_rows) + 1, point, filtered)
                )

        for line in lines:
            if "data required time" in line:
                parts = line.split("data required time", 1)
                if len(parts) == 2:
                    tok = parts[0].strip().split()
                    if tok:
                        meta["required_time"] = tok[-1]
                break

        return meta, launch_rows, capture_rows

    def _values_by_columns(self, content: str, col_pos: dict[str, int]) -> dict[str, str]:
        """按列位置切片得到各属性原始值，不用正则。"""
        ordered = sorted(
            [n for n in self.attrs_order if n in col_pos],
            key=lambda x: col_pos[x],
        )
        if not ordered:
            return {}
        out: dict[str, str] = {}
        for i, name in enumerate(ordered):
            start = col_pos[name]
            end = col_pos[ordered[i + 1]] if i + 1 < len(ordered) else len(content)
            value = content[start:end].strip() if start < end else ""
            if value in ("-", "-0.000"):
                value = ""
            out[name] = value
        return out

    def _parse_line_by_type(
        self, line: str, col_pos: dict[str, int], full_line: str = ""
    ) -> tuple[str, dict[str, str], str]:
        """根据 Type 分派到对应解析方法；仅用列切片与 split，不用正则匹配属性。"""
        content = (full_line or line).rstrip()
        if not content.strip() or "Description" not in col_pos:
            return "", {}, "other"

        raw = self._values_by_columns(content, col_pos)
        type_str = (raw.get("Type") or "").strip().lower()

        # 报告里 pin 需区分为 input_pin / output_pin
        if type_str == "pin":
            desc_col = content[col_pos["Description"] :].strip()
            pin_name = _pin_name_from_desc(desc_col)
            type_str = "output_pin" if pin_name in _OUTPUT_PIN_NAMES else "input_pin"

        parsers = {
            "input_pin": self._parse_input_pin,
            "output_pin": self._parse_output_pin,
            "net": self._parse_net,
            "clock": self._parse_clock,
            "port": self._parse_port,
            "constraint": self._parse_constraint,
            "required": self._parse_required,
            "arrival": self._parse_arrival,
            "slack": self._parse_slack,
        }
        parser = parsers.get(type_str)
        if not parser:
            return "", {}, "other"

        point_name, attrs = parser(raw, content, col_pos)
        return point_name, attrs, type_str

    def _desc_from_content(self, content: str, col_pos: dict[str, int]) -> str:
        """从整行取 Description 列：自列起始到行尾，避免列宽错位。"""
        if "Description" not in col_pos:
            return ""
        return content[col_pos["Description"] :].strip()

    def _desc_from_pin_line(self, content: str) -> str:
        """从 pin/port 行按「Time 与 Description 间为 / 或 \\」取整段 point 名，不依赖列位置，避免前后被截断。"""
        line = content.strip()
        if " / " in line:
            return line.rsplit(" / ", 1)[-1].strip()
        if " \\ " in line:
            return line.rsplit(" \\ ", 1)[-1].strip()
        return ""

    def _parse_input_pin(
        self, raw: dict[str, str], content: str, col_pos: dict[str, int]
    ) -> tuple[str, dict[str, str]]:
        """input pin: D-Trans, Trans, Derate, x-coord, y-coord, D-Delay, Delay, Time, Description。"""
        attrs = {k: "" for k in self.attrs_order}
        derate_raw = (raw.get("Derate") or "").strip()
        if "{" in derate_raw:
            derate_part, x_val, y_val = self._split_derate_and_xy(derate_raw)
            attrs["Derate"] = derate_part
            attrs["x-coord"] = x_val
            attrs["y-coord"] = y_val
        else:
            attrs["Derate"] = derate_raw.replace(" ", "")
            xy_cell = self._xy_cell_from_raw(raw)
            attrs["x-coord"] = self._parse_xy(xy_cell, "x-coord")
            attrs["y-coord"] = self._parse_xy(xy_cell, "y-coord")
        attrs["D-Trans"] = (raw.get("D-Trans") or "").strip()
        attrs["Trans"] = (raw.get("Trans") or "").strip()
        attrs["Type"] = raw.get("Type", "")
        prefix = content[: col_pos["Description"]].strip()
        nums = self._last_numeric_tokens(prefix, 3)
        if len(nums) >= 3:
            attrs["D-Delay"], attrs["Delay"], attrs["Time"] = nums[0], nums[1], nums[2]
        elif len(nums) == 2:
            attrs["Delay"], attrs["Time"] = nums[0], nums[1]
        elif len(nums) == 1:
            attrs["Time"] = nums[0]
        desc = self._desc_from_pin_line(content) or self._desc_from_content(content, col_pos)
        point = _desc_to_point(desc)
        attrs["Description"] = point
        return point, attrs

    def _parse_output_pin(
        self, raw: dict[str, str], content: str, col_pos: dict[str, int]
    ) -> tuple[str, dict[str, str]]:
        """output pin: Trans, Derate, x-coord, y-coord, Delay, Time, Description。"""
        attrs = {k: "" for k in self.attrs_order}
        derate_raw = (raw.get("Derate") or "").strip()
        if "{" in derate_raw:
            derate_part, x_val, y_val = self._split_derate_and_xy(derate_raw)
            attrs["Derate"] = derate_part
            attrs["x-coord"] = x_val
            attrs["y-coord"] = y_val
        else:
            attrs["Derate"] = derate_raw.replace(" ", "")
            xy_cell = self._xy_cell_from_raw(raw)
            attrs["x-coord"] = self._parse_xy(xy_cell, "x-coord")
            attrs["y-coord"] = self._parse_xy(xy_cell, "y-coord")
        attrs["Trans"] = (raw.get("Trans") or "").strip()
        attrs["Type"] = raw.get("Type", "")
        prefix = content[: col_pos["Description"]].strip()
        nums = self._last_numeric_tokens(prefix, 2)
        if len(nums) >= 2:
            attrs["Delay"], attrs["Time"] = nums[0], nums[1]
        elif len(nums) == 1:
            attrs["Time"] = nums[0]
        desc = self._desc_from_pin_line(content) or self._desc_from_content(content, col_pos)
        point = _desc_to_point(desc)
        attrs["Description"] = point
        return point, attrs

    def _xy_cell_from_raw(self, raw: dict[str, str]) -> str:
        """合并 x-coord 与 y-coord 列（表头可能把 { x y } 拆成两列），便于解析出两个坐标值。"""
        x_part = (raw.get("x-coord") or "").strip()
        y_part = (raw.get("y-coord") or "").strip()
        return (x_part + " " + y_part).strip()

    def _split_derate_and_xy(self, derate_cell: str) -> tuple[str, str, str]:
        """当 Derate 列与坐标连在一起（如 1.100,1.100{219.156,772.737}）时拆成 Derate 与 x、y。返回 (derate_clean, x, y)。"""
        s = (derate_cell or "").strip()
        if not s:
            return "", "", ""
        if "{" not in s:
            return s.replace(" ", ""), "", ""
        idx = s.index("{")
        derate_part = s[:idx].strip().replace(" ", "")
        inner = s[idx + 1 :].strip()
        if inner.endswith("}"):
            inner = inner[:-1].strip()
        inner = inner.replace(",", " ")
        parts = inner.split()
        x = parts[0] if len(parts) >= 1 else ""
        y = parts[1] if len(parts) >= 2 else ""
        return derate_part, x, y

    def _parse_xy(self, value: str, which: str) -> str:
        """从合并后的坐标串（如 '{  219.156    772.737}' 或 '{  219.156' + '772.737}'）用 split 取出 x 或 y。"""
        s = value.strip()
        if s.startswith("{"):
            s = s[1:]
        if s.endswith("}"):
            s = s[:-1]
        s = s.strip()
        if not s:
            return ""
        parts = s.split()
        if which == "x-coord" and len(parts) >= 1:
            return parts[0]
        if which == "y-coord" and len(parts) >= 2:
            return parts[1]
        return ""

    def _parse_net(
        self, raw: dict[str, str], content: str, col_pos: dict[str, int]
    ) -> tuple[str, dict[str, str]]:
        """net: Fanout, Cap, Description。用 split：Type 后为 Fanout、Cap（可能跟 xd）、再后为 Description。"""
        attrs = {k: "" for k in self.attrs_order}
        attrs["Type"] = raw.get("Type", "")
        tokens = content.split()
        if len(tokens) < 2:
            return "", attrs
        rest = tokens[1:]
        attrs["Fanout"] = rest[0] if rest else ""
        if len(rest) >= 2:
            attrs["Cap"] = rest[1].split()[0]
        # Cap 后可能跟 xd，再后才是 net 名
        desc_start = 2
        if len(rest) > 3 and rest[2].lower() == "xd":
            desc_start = 3
        desc = " ".join(rest[desc_start:]) if len(rest) > desc_start else ""
        point = _desc_to_point(desc)
        attrs["Description"] = point
        return point, attrs

    def _last_numeric_tokens(self, text: str, n: int) -> list[str]:
        """从文本中取最后 n 个“像数字”的 token（用 split，不用正则）。"""
        parts = text.strip().split()
        out: list[str] = []
        for i in range(len(parts) - 1, -1, -1):
            if len(out) >= n:
                break
            s = parts[i]
            if not s:
                continue
            if s.lstrip("-").replace(".", "", 1).isdigit():
                out.append(s)
        out.reverse()
        return out

    def _parse_clock(
        self, raw: dict[str, str], content: str, col_pos: dict[str, int]
    ) -> tuple[str, dict[str, str]]:
        """clock: Delay, Time, Description。用 split 取行尾两数及之后为描述。"""
        attrs = {k: "" for k in self.attrs_order}
        attrs["Type"] = raw.get("Type", "")
        values, desc = _tail_n_numeric_and_desc(content, 2)
        if len(values) >= 2:
            attrs["Delay"], attrs["Time"] = values[0], values[1]
        elif len(values) == 1:
            attrs["Time"] = values[0]
        point = _desc_to_point(desc)
        attrs["Description"] = point
        return point, attrs

    def _parse_port(
        self, raw: dict[str, str], content: str, col_pos: dict[str, int]
    ) -> tuple[str, dict[str, str]]:
        """port: Trans, x-coord, y-coord, Delay, Time, Description（Time 与 Description 间可有 / 或 \\）。"""
        attrs = {k: "" for k in self.attrs_order}
        attrs["Type"] = raw.get("Type", "")
        attrs["Trans"] = (raw.get("Trans") or "").strip()
        derate_raw = (raw.get("Derate") or "").strip()
        if "{" in derate_raw:
            _, x_val, y_val = self._split_derate_and_xy(derate_raw)
            attrs["x-coord"] = x_val
            attrs["y-coord"] = y_val
        else:
            xy_cell = self._xy_cell_from_raw(raw)
            attrs["x-coord"] = self._parse_xy(xy_cell, "x-coord")
            attrs["y-coord"] = self._parse_xy(xy_cell, "y-coord")
        values, desc = _tail_n_numeric_and_desc(content, 2)
        if len(values) >= 2:
            attrs["Delay"], attrs["Time"] = values[0], values[1]
        elif len(values) == 1:
            attrs["Time"] = values[0]
        desc = self._desc_from_pin_line(content) or desc
        point = _desc_to_point(desc)
        attrs["Description"] = point
        return point, attrs

    def _parse_constraint(
        self, raw: dict[str, str], content: str, col_pos: dict[str, int]
    ) -> tuple[str, dict[str, str]]:
        """constraint: Delay, Time, Description。"""
        attrs = {k: "" for k in self.attrs_order}
        attrs["Type"] = raw.get("Type", "")
        values, desc = _tail_n_numeric_and_desc(content, 2)
        if len(values) >= 2:
            attrs["Delay"], attrs["Time"] = values[0], values[1]
        elif len(values) == 1:
            attrs["Time"] = values[0]
        point = _desc_to_point(desc)
        attrs["Description"] = point
        return point, attrs

    def _parse_required(
        self, raw: dict[str, str], content: str, col_pos: dict[str, int]
    ) -> tuple[str, dict[str, str]]:
        """required: Time, Description。"""
        attrs = {k: "" for k in self.attrs_order}
        attrs["Type"] = raw.get("Type", "")
        values, desc = _tail_n_numeric_and_desc(content, 1)
        if values:
            attrs["Time"] = values[0]
        point = _desc_to_point(desc)
        attrs["Description"] = point
        return point, attrs

    def _parse_arrival(
        self, raw: dict[str, str], content: str, col_pos: dict[str, int]
    ) -> tuple[str, dict[str, str]]:
        """arrival: Time, Description。"""
        attrs = {k: "" for k in self.attrs_order}
        attrs["Type"] = raw.get("Type", "")
        values, desc = _tail_n_numeric_and_desc(content, 1)
        if values:
            attrs["Time"] = values[0]
        point = _desc_to_point(desc)
        attrs["Description"] = point
        return point, attrs

    def _parse_slack(
        self, raw: dict[str, str], content: str, col_pos: dict[str, int]
    ) -> tuple[str, dict[str, str]]:
        """slack: Time, Description。"""
        attrs = {k: "" for k in self.attrs_order}
        attrs["Type"] = raw.get("Type", "")
        values, desc = _tail_n_numeric_and_desc(content, 1)
        if values:
            attrs["Time"] = values[0]
        point = _desc_to_point(desc)
        attrs["Description"] = point
        return point, attrs
