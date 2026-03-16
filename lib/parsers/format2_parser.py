"""
Format2 Timing 报告解析器。

列含 Type/Fanout/Cap/D-Trans/Trans/Derate/x-coord/y-coord/D-Delay/Delay/Time/Description；
按 Path Start/Path End 分块，按 Type 与 Description 列解析 pin/net/clock/port 等行，
并处理 Derate、坐标、slack、arrival/required 等语义。
"""
from __future__ import annotations

import re
from typing import Any

from .time_parser_base import TimeParser


def _descToPoint(desc: str) -> str:
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
    while s and s[0] in " {}0123456789.-":
        s = s[1:].lstrip()
    return s.strip()


def _pinNameFromDesc(desc: str) -> str:
    s = _descToPoint(desc)
    if " (" in s:
        s = s.split(" (", 1)[0]
    if "/" in s:
        s = s.split("/")[-1]
    if "\\" in s:
        s = s.split("\\")[-1]
    return s.strip()


def _isNumericToken(s: str) -> bool:
    s = s.strip()
    if not s:
        return False
    t = s.lstrip("-")
    return t.replace(".", "", 1).isdigit()


def _tailNNumericAndDesc(line: str, n: int) -> tuple[list[str], str]:
    tokens = line.split()
    if len(tokens) <= 1:
        return [], ""
    rest = tokens[1:]
    indices: list[int] = []
    for j in range(len(rest) - 1, -1, -1):
        if _isNumericToken(rest[j]):
            indices.append(j)
            if len(indices) == n:
                break
    if len(indices) < n:
        return [], " ".join(rest)
    values = [rest[i] for i in sorted(indices)]
    last_idx = max(indices)
    desc = " ".join(rest[last_idx + 1 :])
    return values, desc


_OUTPUT_PIN_NAMES = frozenset({"Q", "Z", "ZN", "ZP"})


class Format2Parser(TimeParser):
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
        "trigger_edge",
        "Description",
    ]
    skip_first_rows = 4
    default_attrs_by_type = {
        "input_pin": ["Type", "D-Trans", "Trans", "Derate", "x-coord", "y-coord", "D-Delay", "Delay", "Time", "trigger_edge", "Description"],
        "output_pin": ["Type", "Trans", "Derate", "x-coord", "y-coord", "Delay", "Time", "trigger_edge", "Description"],
        "net": ["Type", "Fanout", "Cap", "Description"],
        "clock": ["Type", "Delay", "Time", "Description"],
        "port": ["Type", "Trans", "x-coord", "y-coord", "Delay", "Time", "trigger_edge", "Description"],
        "constraint": ["Type", "Delay", "Time", "Description"],
        "required": ["Type", "Time", "Description"],
        "arrival": ["Type", "Time", "Description"],
        "slack": ["Type", "Time", "Description"],
    }

    _re_path_start = re.compile(r"^\s*Path Start\s+:\s+(.+?)\s+\(\s*flip-flop[^)]*,\s*(\w+)\s*\)\s*$")
    _re_path_end = re.compile(r"^\s*Path End\s+:\s+(.+?)\s+\(\s*flip-flop[^)]*,\s*(\w+)\s*\)\s*$")
    _re_slack_value_before = re.compile(r"(-?\d+(?:\.\d+)?)\s+slack\s*\(", re.IGNORECASE)
    _re_slack_value_after = re.compile(r"slack\s*\(\w+\)\s*[:=]?\s*(-?\d+(?:\.\d+)?)", re.IGNORECASE)
    _re_slack_status = re.compile(r"slack\s*\((\w+)\)", re.IGNORECASE)
    _re_slack_line = re.compile(r"slack\s*\((?:violated|met)\)", re.IGNORECASE)
    _re_sep = re.compile(r"^-=+\s*$")
    _re_data_arrival = re.compile(r"data arrival time", re.IGNORECASE)

    def scanPathBlocks(self, report_path: str) -> list[tuple[int, str]]:
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
                    if self._re_slack_line.search(lines[i]):
                        i += 1
                        break
                    i += 1
                blocks.append((path_id, "".join(lines[start_i:i])))
                continue
            i += 1
        return blocks

    def parseOnePath(
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
            "uncertainty": "",
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
            if self._re_slack_line.search(line):
                vm = self._re_slack_value_before.search(line) or self._re_slack_value_after.search(line)
                sm = self._re_slack_status.search(line)
                if vm:
                    meta["slack"] = vm.group(1).strip()
                else:
                    # 兜底：取该行最后一个数值
                    nums = re.findall(r"-?\d+(?:\.\d+)?", line)
                    if nums:
                        meta["slack"] = nums[-1]
                if sm:
                    meta["slack_status"] = sm.group(1).strip().upper()
                break

        col_pos: dict[str, int] = {}
        table_start = 0
        for idx, line in enumerate(lines):
            if "Type" in line and "Fanout" in line and "Cap" in line:
                col_pos = self.extractColumnPositions(line, self.attrs_order)
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

            point, attrs, point_type = self._parseLineByType(lines[j], col_pos, lines[j])
            if not point and point_type not in ("required", "arrival", "slack"):
                continue

            seg_idx = len(launch_rows) if in_launch else len(capture_rows)
            filtered = self.applyTypeFilter(attrs, point_type, seg_idx)

            if self._re_data_arrival.search(lines[j]):
                if in_launch:
                    vm = re.search(r"(-?\d+\.\d+)\s+data\s+arrival\s+time", lines[j], re.IGNORECASE)
                    if vm:
                        meta["arrival_time"] = vm.group(1).strip()
                launch_rows.append(self.buildPointRow(meta, len(launch_rows) + 1, point, filtered))
                in_launch = False
                in_capture = True
                continue

            if in_launch:
                launch_rows.append(self.buildPointRow(meta, len(launch_rows) + 1, point, filtered))
            elif in_capture:
                capture_rows.append(self.buildPointRow(meta, len(capture_rows) + 1, point, filtered))

        for line in lines:
            if "data required time" in line:
                vm = re.search(r"(-?\d+\.\d+)\s+data\s+required\s+time", line, re.IGNORECASE)
                if vm:
                    meta["required_time"] = vm.group(1).strip()
                break

        if not meta["arrival_time"]:
            for r in launch_rows:
                if (r.get("point") or "").strip().lower() == "data arrival time":
                    t = str(r.get("Time") or "").strip()
                    if t and t not in ("/", "\\"):
                        meta["arrival_time"] = t
                        break
        if not meta["required_time"]:
            for r in capture_rows:
                if (r.get("point") or "").strip().lower() == "data required time":
                    t = str(r.get("Time") or "").strip()
                    if t and t not in ("/", "\\"):
                        meta["required_time"] = t
                        break

        self._fillUncertainty(lines, meta)
        return meta, launch_rows, capture_rows

    def _valuesByColumns(self, content: str, col_pos: dict[str, int]) -> dict[str, str]:
        ordered = sorted([n for n in self.attrs_order if n in col_pos], key=lambda x: col_pos[x])
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

    def _descFromContent(self, content: str, col_pos: dict[str, int]) -> str:
        if "Description" not in col_pos:
            return ""
        return content[col_pos["Description"] :].strip()

    def _descFromPinLine(self, content: str) -> str:
        line = content.strip()
        if " / " in line:
            return line.rsplit(" / ", 1)[-1].strip()
        if " \\ " in line:
            return line.rsplit(" \\ ", 1)[-1].strip()
        return ""

    def _triggerEdgeFromLine(self, content: str) -> str:
        line = content.strip()
        if " / " in line:
            return "r"
        if " \\ " in line:
            return "f"
        return ""

    def _parseLineByType(self, line: str, col_pos: dict[str, int], full_line: str = "") -> tuple[str, dict[str, str], str]:
        content = (full_line or line).rstrip()
        if not content.strip() or "Description" not in col_pos:
            return "", {}, "other"
        raw = self._valuesByColumns(content, col_pos)
        type_str = (raw.get("Type") or "").strip().lower()
        if type_str == "pin":
            desc_col = content[col_pos["Description"] :].strip()
            pin_name = _pinNameFromDesc(desc_col)
            type_str = "output_pin" if pin_name in _OUTPUT_PIN_NAMES else "input_pin"
        parsers = {
            "input_pin": self._parseInputPin,
            "output_pin": self._parseOutputPin,
            "net": self._parseNet,
            "clock": self._parseClock,
            "port": self._parsePort,
            "constraint": self._parseConstraint,
            "required": self._parseRequired,
            "arrival": self._parseArrival,
            "slack": self._parseSlack,
        }
        parser = parsers.get(type_str)
        if not parser:
            return "", {}, "other"
        point_name, attrs = parser(raw, content, col_pos)
        return point_name, attrs, type_str

    def _splitDerateAndXy(self, derate_cell: str) -> tuple[str, str, str]:
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

    def _xyCellFromRaw(self, raw: dict[str, str]) -> str:
        return ((raw.get("x-coord") or "").strip() + " " + (raw.get("y-coord") or "").strip()).strip()

    def _parseXy(self, value: str, which: str) -> str:
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

    def _lastNumericTokens(self, text: str, n: int) -> list[str]:
        parts = text.strip().split()
        out: list[str] = []
        for i in range(len(parts) - 1, -1, -1):
            if len(out) >= n:
                break
            s = parts[i]
            if s and s.lstrip("-").replace(".", "", 1).isdigit():
                out.append(s)
        out.reverse()
        return out

    def _extractPinMetrics(self, content: str, is_output: bool) -> tuple[str, str, str, str, str, str, str]:
        """
        从完整 pin 行稳健提取:
        (trans, derate, x, y, d_delay, delay, time)
        通过坐标块和数值顺序定位，避免把 x/y 坐标误当作 Delay/Time。
        """
        trans = ""
        derate = ""
        x_val = ""
        y_val = ""
        d_delay = ""
        delay = ""
        time = ""

        coord_m = re.search(r"\{\s*(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s*\}", content)
        prefix = content
        if coord_m:
            x_val, y_val = coord_m.group(1), coord_m.group(2)
            prefix = content[: coord_m.start()] + content[coord_m.end() :]

        derate_m = re.search(r"(\d+(?:\.\d+)?,\d+(?:\.\d+)?)\s*(?:\{|$)", content)
        if derate_m:
            derate = derate_m.group(1).strip()
            prefix = prefix.replace(derate, " ")

        nums = re.findall(r"-?\d+(?:\.\d+)?", prefix)
        if nums:
            if is_output:
                # output_pin 典型数值顺序: Trans, Delay, Time
                if len(nums) >= 3:
                    trans, delay, time = nums[-3], nums[-2], nums[-1]
                elif len(nums) == 2:
                    delay, time = nums[-2], nums[-1]
                elif len(nums) == 1:
                    time = nums[-1]
            else:
                # input_pin 典型数值顺序: D-Trans, Trans, D-Delay, Delay, Time
                if len(nums) >= 5:
                    trans = nums[-4]
                    d_delay, delay, time = nums[-3], nums[-2], nums[-1]
                elif len(nums) >= 3:
                    delay, time = nums[-2], nums[-1]
                elif len(nums) == 2:
                    delay, time = nums[-2], nums[-1]
                elif len(nums) == 1:
                    time = nums[-1]

        return trans, derate, x_val, y_val, d_delay, delay, time

    def _isReasonableNum(self, s: str, max_abs: float = 10.0) -> bool:
        try:
            v = float(str(s).strip())
            return abs(v) <= max_abs
        except Exception:
            return False

    def _parseInputPin(self, raw: dict[str, str], content: str, col_pos: dict[str, int]) -> tuple[str, dict[str, str]]:
        attrs = {k: "" for k in self.attrs_order}
        prefix_area = content[: col_pos["Description"]] if "Description" in col_pos else content
        trans, derate, x_val, y_val, d_delay, delay, time = self._extractPinMetrics(prefix_area, is_output=False)
        attrs["Derate"] = derate or (raw.get("Derate") or "").strip().replace(" ", "")
        attrs["x-coord"] = x_val or self._parseXy(self._xyCellFromRaw(raw), "x-coord")
        attrs["y-coord"] = y_val or self._parseXy(self._xyCellFromRaw(raw), "y-coord")
        raw_dtrans = (raw.get("D-Trans") or "").strip()
        raw_trans = (raw.get("Trans") or "").strip()
        attrs["D-Trans"] = raw_dtrans if self._isReasonableNum(raw_dtrans, 1.0) else ""
        attrs["Trans"] = trans if self._isReasonableNum(trans, 1.0) else (raw_trans if self._isReasonableNum(raw_trans, 1.0) else "")
        attrs["Type"] = raw.get("Type", "")
        raw_ddelay = (raw.get("D-Delay") or "").strip()
        raw_delay = (raw.get("Delay") or "").strip()
        raw_time = (raw.get("Time") or "").strip()
        attrs["D-Delay"] = d_delay if self._isReasonableNum(d_delay, 2.0) else (raw_ddelay if self._isReasonableNum(raw_ddelay, 2.0) else "")
        attrs["Delay"] = delay if self._isReasonableNum(delay, 10.0) else (raw_delay if self._isReasonableNum(raw_delay, 10.0) else "")
        attrs["Time"] = time if self._isReasonableNum(time, 20.0) else (raw_time if self._isReasonableNum(raw_time, 20.0) else "")
        attrs["trigger_edge"] = self._triggerEdgeFromLine(content)
        desc = self._descFromPinLine(content) or self._descFromContent(content, col_pos)
        point = _descToPoint(desc)
        attrs["Description"] = point
        return point, attrs

    def _parseOutputPin(self, raw: dict[str, str], content: str, col_pos: dict[str, int]) -> tuple[str, dict[str, str]]:
        attrs = {k: "" for k in self.attrs_order}
        prefix_area = content[: col_pos["Description"]] if "Description" in col_pos else content
        trans, derate, x_val, y_val, _d_delay, delay, time = self._extractPinMetrics(prefix_area, is_output=True)
        attrs["Derate"] = derate or (raw.get("Derate") or "").strip().replace(" ", "")
        attrs["x-coord"] = x_val or self._parseXy(self._xyCellFromRaw(raw), "x-coord")
        attrs["y-coord"] = y_val or self._parseXy(self._xyCellFromRaw(raw), "y-coord")
        raw_trans = (raw.get("Trans") or "").strip()
        attrs["Trans"] = trans if self._isReasonableNum(trans, 1.0) else (raw_trans if self._isReasonableNum(raw_trans, 1.0) else "")
        attrs["Type"] = raw.get("Type", "")
        raw_delay = (raw.get("Delay") or "").strip()
        raw_time = (raw.get("Time") or "").strip()
        attrs["Delay"] = delay if self._isReasonableNum(delay, 10.0) else (raw_delay if self._isReasonableNum(raw_delay, 10.0) else "")
        attrs["Time"] = time if self._isReasonableNum(time, 20.0) else (raw_time if self._isReasonableNum(raw_time, 20.0) else "")
        attrs["trigger_edge"] = self._triggerEdgeFromLine(content)
        desc = self._descFromPinLine(content) or self._descFromContent(content, col_pos)
        point = _descToPoint(desc)
        attrs["Description"] = point
        return point, attrs

    def _parseNet(self, raw: dict[str, str], content: str, col_pos: dict[str, int]) -> tuple[str, dict[str, str]]:
        attrs = {k: "" for k in self.attrs_order}
        attrs["Type"] = raw.get("Type", "")
        tokens = content.split()
        if len(tokens) < 2:
            return "", attrs
        rest = tokens[1:]
        attrs["Fanout"] = rest[0] if rest else ""
        if len(rest) >= 2:
            attrs["Cap"] = rest[1].split()[0]
        desc_start = 2
        if len(rest) > 3 and rest[2].lower() == "xd":
            desc_start = 3
        desc = " ".join(rest[desc_start:]) if len(rest) > desc_start else ""
        point = _descToPoint(desc)
        attrs["Description"] = point
        return point, attrs

    def _parseClock(self, raw: dict[str, str], content: str, col_pos: dict[str, int]) -> tuple[str, dict[str, str]]:
        attrs = {k: "" for k in self.attrs_order}
        attrs["Type"] = raw.get("Type", "")
        values, desc = _tailNNumericAndDesc(content, 2)
        if len(values) >= 2:
            attrs["Delay"], attrs["Time"] = values[0], values[1]
        elif len(values) == 1:
            attrs["Time"] = values[0]
        point = _descToPoint(desc)
        attrs["Description"] = point
        return point, attrs

    def _parsePort(self, raw: dict[str, str], content: str, col_pos: dict[str, int]) -> tuple[str, dict[str, str]]:
        attrs = {k: "" for k in self.attrs_order}
        attrs["Type"] = raw.get("Type", "")
        attrs["Trans"] = (raw.get("Trans") or "").strip()
        derate_raw = (raw.get("Derate") or "").strip()
        if "{" in derate_raw:
            _, x_val, y_val = self._splitDerateAndXy(derate_raw)
            attrs["x-coord"] = x_val
            attrs["y-coord"] = y_val
        else:
            xy_cell = self._xyCellFromRaw(raw)
            attrs["x-coord"] = self._parseXy(xy_cell, "x-coord")
            attrs["y-coord"] = self._parseXy(xy_cell, "y-coord")
        raw_delay = (raw.get("Delay") or "").strip()
        raw_time = (raw.get("Time") or "").strip()
        values, desc = _tailNNumericAndDesc(content, 2)
        if len(values) >= 2:
            attrs["Delay"], attrs["Time"] = values[0], values[1]
        else:
            attrs["Delay"], attrs["Time"] = raw_delay, raw_time
        attrs["trigger_edge"] = self._triggerEdgeFromLine(content)
        desc = self._descFromPinLine(content) or desc
        point = _descToPoint(desc)
        attrs["Description"] = point
        return point, attrs

    def _parseConstraint(self, raw: dict[str, str], content: str, col_pos: dict[str, int]) -> tuple[str, dict[str, str]]:
        attrs = {k: "" for k in self.attrs_order}
        attrs["Type"] = raw.get("Type", "")
        values, desc = _tailNNumericAndDesc(content, 2)
        if len(values) >= 2:
            attrs["Delay"], attrs["Time"] = values[0], values[1]
        elif len(values) == 1:
            attrs["Time"] = values[0]
        point = _descToPoint(desc)
        attrs["Description"] = point
        return point, attrs

    def _parseRequired(self, raw: dict[str, str], content: str, col_pos: dict[str, int]) -> tuple[str, dict[str, str]]:
        attrs = {k: "" for k in self.attrs_order}
        attrs["Type"] = raw.get("Type", "")
        values, desc = _tailNNumericAndDesc(content, 1)
        if values:
            attrs["Time"] = values[0]
        point = _descToPoint(desc)
        attrs["Description"] = point
        return point, attrs

    def _parseArrival(self, raw: dict[str, str], content: str, col_pos: dict[str, int]) -> tuple[str, dict[str, str]]:
        attrs = {k: "" for k in self.attrs_order}
        attrs["Type"] = raw.get("Type", "")
        values, desc = _tailNNumericAndDesc(content, 1)
        if values:
            attrs["Time"] = values[0]
        point = _descToPoint(desc)
        attrs["Description"] = point
        return point, attrs

    def _parseSlack(self, raw: dict[str, str], content: str, col_pos: dict[str, int]) -> tuple[str, dict[str, str]]:
        attrs = {k: "" for k in self.attrs_order}
        attrs["Type"] = raw.get("Type", "")
        values, desc = _tailNNumericAndDesc(content, 1)
        if values:
            attrs["Time"] = values[0]
        point = _descToPoint(desc)
        attrs["Description"] = point
        return point, attrs

