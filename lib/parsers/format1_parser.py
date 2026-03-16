"""
Format1（APR 风格）Timing 报告解析器。

解析流程：按 Startpoint 行分块 → 每块内解析表头与 Point 表 → 用 clock/data arrival/library setup
边界区分 launch 与 capture 段，固定列宽提取 Fanout/Cap/Trans/Location/Incr/Path/trigger_edge。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from .time_parser_base import TimeParser


class Format1Parser(TimeParser):
    """Format1(APR) 报告解析器。表头含 Point, Fanout, Cap, Trans, Location, Incr, Path；launch/capture 按 clock 与 data arrival 边界划分。"""

    default_attrs_order = ["Fanout", "Cap", "Trans", "Location", "Incr", "Path", "trigger_edge"]
    skip_first_rows = 2
    default_attrs_by_type = {
        "net": ["Fanout"],
        "input_pin": ["Cap", "Trans", "Location", "Incr", "Path", "trigger_edge"],
        "output_pin": ["Cap", "Trans", "Location", "Incr", "Path", "trigger_edge"],
    }

    _output_pin_names = frozenset({"Q", "Z", "ZN", "ZP"})

    _re_startpoint = re.compile(r"^\s*Startpoint:\s+(.+?)\s+\(.+\)\s*$")
    _re_endpoint = re.compile(r"^\s*Endpoint:\s+(.+?)\s+\(.+\)\s*$")
    _re_clocked_by = re.compile(r"clocked by ([^\s)]+)")
    _re_slack = re.compile(r"^\s*slack\s+\((VIOLATED|MET)\)(?:\s|$)")
    _re_slack_value = re.compile(r"(-?\d+\.\d+)\s*$")
    _re_point_header = re.compile(r"^\s*Point\s+", re.IGNORECASE)
    _re_sep_line = re.compile(r"^\s*-{3,}\s*$")
    _re_clock_start = re.compile(
        r"^\s*clock\s+\S+(?:\s+\((?:rise|fall)\s+edge\))?\s+(?=[-\d])",
        re.IGNORECASE,
    )
    _re_data_arrival = re.compile(r"^\s*data\s+arrival\s+time(?:\s|$)")
    _re_library_setup = re.compile(r"^\s*library\s+setup\s+time(?:\s|$)")

    def scanPathBlocks(self, report_path: str) -> list[tuple[int, str]]:
        """按 Startpoint 行切分 path 块，返回 [(path_id, path_text), ...]。"""
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

    def parseOnePath(
        self, path_id: int, path_text: str
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
        """
        解析单条 path：先提取 meta（startpoint/endpoint/slack 等），再定位 Point 表头与列位置，
        按 clock / data arrival / library setup 边界解析 launch 与 capture 表格行。
        """
        lines = path_text.splitlines()
        meta = self._defaultMeta(path_id)
        launch_rows: list[dict[str, Any]] = []
        capture_rows: list[dict[str, Any]] = []

        self._fillMetaFromHeader(lines, meta)
        col_pos, table_start = self._findTableStart(lines)
        self._parseLaunchSegment(lines, meta, col_pos, table_start, launch_rows)
        self._parseCaptureSegment(lines, meta, col_pos, table_start, capture_rows)
        self._fillRequiredAndArrival(lines, meta)
        self._fillUncertainty(lines, meta)

        return meta, launch_rows, capture_rows

    @staticmethod
    def _defaultMeta(path_id: int) -> dict[str, Any]:
        """返回单 path 的默认 meta 字典。"""
        return {
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

    def _fillMetaFromHeader(self, lines: list[str], meta: dict[str, Any]) -> None:
        """从 path 文本前部解析 Startpoint/Endpoint/slack 等写入 meta。"""
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

    def _findTableStart(self, lines: list[str]) -> tuple[dict[str, int], int]:
        """定位 Point 表头行与列位置，返回 (col_pos, table_start_row)。"""
        col_pos: dict[str, int] = {}
        table_start = 0
        for idx, line in enumerate(lines):
            if self._re_point_header.match(line):
                col_pos = self.extractColumnPositions(line, self.attrs_order)
                if "Location" in col_pos:
                    table_start = idx + 1
                    if table_start < len(lines) and self._re_sep_line.match(lines[table_start]):
                        table_start += 1
                    break
                col_pos = {}
        return col_pos, table_start

    def _classify_row_kind(
        self,
        point: str,
        line: str,
        segment_row_index: int,
        in_launch: bool,
    ) -> str:
        """
        根据行内容与 point 名粗略分类当前点表行为:
        - clock: clock 行
        - net:   含 (net) 的行
        - pin:   其余 pin 行
        其他返回空串，表示沿用定宽解析结果。
        """
        if self._re_clock_start.match(line):
            return "clock"
        if "(net)" in (point or ""):
            return "net"
        if in_launch and segment_row_index >= 0:
            return "pin"
        return ""

    def _parseNumericColumns(
        self,
        line: str,
        col_pos: dict[str, int],
        row_kind: str,
    ) -> Dict[str, str] | None:
        """
        基于 row_kind + 数值 token 顺序解析当前行的数值列。

        若无法可靠映射（无数字或 row_kind 未知），返回 None，调用方应回退到 parseFixedWidthAttrs 的 attrs。
        """
        # 行类型未知时不启用数值映射
        if not row_kind:
            return None
        tokens = re.findall(r"-?\d+(?:\.\d+)?", line)
        if not tokens:
            return None

        # 只针对易截断的 Incr/Path 做“数值顺序”解析，Cap/Trans/Fanout 仍由定宽解析负责，
        # 以兼顾内部生成报告与外部 APR 报告。
        attrs: Dict[str, str] = {name: "" for name in self.attrs_order}
        if row_kind == "clock":
            if len(tokens) >= 2:
                attrs["Incr"] = tokens[-2]
                attrs["Path"] = tokens[-1]
            elif len(tokens) == 1:
                attrs["Path"] = tokens[-1]
            return attrs

        if row_kind == "net":
            # 保留 Fanout/Cap 的定宽结果，仅从尾部补 Incr/Path，避免被坐标截断
            if len(tokens) >= 2:
                attrs["Incr"] = tokens[-2]
                attrs["Path"] = tokens[-1]
            elif len(tokens) == 1:
                attrs["Path"] = tokens[-1]
            return attrs

        if row_kind == "pin":
            # 典型行模式：
            #   ... Cap  Trans   (x, y)   Incr   Path edge
            # 只用最后两个数字推导 Incr/Path，Cap/Trans 仍用定宽解析结果。
            if len(tokens) >= 2:
                attrs["Incr"] = tokens[-2]
                attrs["Path"] = tokens[-1]
            elif len(tokens) == 1:
                attrs["Path"] = tokens[-1]
            return attrs

        # 未知 row_kind，回退
        return attrs

    def _parseLaunchSegment(
        self,
        lines: list[str],
        meta: dict[str, Any],
        col_pos: dict[str, int],
        table_start: int,
        launch_rows: list[dict[str, Any]],
    ) -> None:
        """从表格区解析 launch 段（从 clock 行到 data arrival time 行）。"""
        in_launch = False
        launch_start_idx = -1
        for j in range(table_start, len(lines)):
            line = lines[j]
            if self._re_clock_start.match(line):
                in_launch = True
                launch_start_idx = j
                continue
            if in_launch and self._re_data_arrival.match(line):
                for k in range(launch_start_idx, j + 1):
                    raw_point, base_attrs = self.parseFixedWidthAttrs(
                        lines[k], col_pos, self.attrs_order
                    )
                    if not raw_point:
                        continue
                    row_kind = self._classify_row_kind(
                        raw_point, lines[k], k - launch_start_idx, in_launch=True
                    )
                    smart_numeric = self._parseNumericColumns(lines[k], col_pos, row_kind)
                    attrs = base_attrs.copy()
                    if smart_numeric:
                        for col, val in smart_numeric.items():
                            if val:
                                attrs[col] = val
                    ptype = self._inferPointType(raw_point)
                    if ptype in ("input_pin", "output_pin"):
                        attrs = self._extractTriggerEdgeFromPath(attrs)
                        if not attrs.get("trigger_edge"):
                            attrs["trigger_edge"] = self._extractTriggerEdgeFromLine(lines[k])
                    filtered = self.applyTypeFilter(attrs, ptype, k - launch_start_idx)
                    launch_rows.append(
                        self.buildPointRow(
                            meta, len(launch_rows) + 1, raw_point, filtered
                        )
                    )
                vm = re.search(r"(-?\d+\.\d+)\s*$", line)
                if vm:
                    meta["arrival_time"] = vm.group(1).strip()
                break

    def _parseCaptureSegment(
        self,
        lines: list[str],
        meta: dict[str, Any],
        col_pos: dict[str, int],
        table_start: int,
        capture_rows: list[dict[str, Any]],
    ) -> None:
        """从表格区解析 capture 段（data arrival 之后的 clock 行到 library setup 行）。"""
        after_data_arrival = False
        in_capture = False
        capture_start_idx = -1
        for j in range(table_start, len(lines)):
            line = lines[j]
            if self._re_data_arrival.match(line):
                after_data_arrival = True
                continue
            if after_data_arrival and self._re_clock_start.match(line):
                in_capture = True
                capture_start_idx = j
                continue
            if in_capture and self._re_library_setup.match(line):
                for k in range(capture_start_idx, j):
                    raw_point, base_attrs = self.parseFixedWidthAttrs(
                        lines[k], col_pos, self.attrs_order
                    )
                    if not raw_point:
                        continue
                    row_kind = self._classify_row_kind(
                        raw_point, lines[k], k - capture_start_idx, in_launch=False
                    )
                    smart_numeric = self._parseNumericColumns(lines[k], col_pos, row_kind)
                    attrs = base_attrs.copy()
                    if smart_numeric:
                        for col, val in smart_numeric.items():
                            if val:
                                attrs[col] = val
                    ptype = self._inferPointType(raw_point)
                    if ptype in ("input_pin", "output_pin"):
                        attrs = self._extractTriggerEdgeFromPath(attrs)
                        if not attrs.get("trigger_edge"):
                            attrs["trigger_edge"] = self._extractTriggerEdgeFromLine(lines[k])
                    filtered = self.applyTypeFilter(attrs, ptype, k - capture_start_idx)
                    capture_rows.append(
                        self.buildPointRow(
                            meta, len(capture_rows) + 1, raw_point, filtered
                        )
                    )
                break

    def _fillRequiredAndArrival(self, lines: list[str], meta: dict[str, Any]) -> None:
        """从行文本中补全 data required time / data arrival time（若前面未填）。"""
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

    @staticmethod
    def _extractTriggerEdgeFromPath(attrs: dict[str, Any]) -> dict[str, Any]:
        """从 Path 列末尾提取 r/f 作为 trigger_edge，并从 Path 中移除该后缀。"""
        path_val = str(attrs.get("Path", "") or "").strip()
        if not path_val:
            attrs["trigger_edge"] = ""
            return attrs
        tokens = path_val.split()
        if tokens and tokens[-1] in ("r", "f"):
            edge = tokens[-1]
            attrs["trigger_edge"] = edge
            attrs["Path"] = " ".join(tokens[:-1])
        else:
            attrs.setdefault("trigger_edge", "")
        return attrs

    @staticmethod
    def _extractTriggerEdgeFromLine(line: str) -> str:
        """从整行末尾提取 trigger_edge（r/f）。"""
        m = re.search(r"\s([rf])\s*$", line.strip(), re.IGNORECASE)
        return m.group(1).lower() if m else ""

    def _inferPointType(self, point_name: str) -> str:
        """根据 point 名称推断类型：net / output_pin / input_pin。"""
        if not point_name or "(net)" in point_name:
            return "net"
        m = re.search(r"/([A-Za-z0-9_\[\]]+)\s*\(?[A-Z]?", point_name)
        pin = m.group(1) if m else ""
        if pin in self._output_pin_names:
            return "output_pin"
        return "input_pin"
