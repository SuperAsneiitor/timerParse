"""
Format1（APR 风格）Timing 报告解析器。

解析流程：按 Startpoint 行分块 → 每块内解析表头与 Point 表 → 用 clock/data arrival/library setup
边界区分 launch 与 capture 段，固定列宽提取 Fanout/Derate/Cap/Trans/Location/Incr/Path/trigger_edge。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from .time_parser_base import TimeParser
from .layout_runtime import LayoutRuntime


class Format1Parser(TimeParser):
    """Format1(APR) 报告解析器。"""

    def __init__(self, attrs_order: list[str] | None = None, attrs_by_type: dict[str, list[str]] | None = None) -> None:
        super().__init__(attrs_order, attrs_by_type)
        self._layout_runtime = LayoutRuntime("format1")

    default_attrs_order = [
        "Fanout",
        "Derate",
        "DerateA",
        "DerateB",
        "Cap",
        "D-Trans",
        "TransMean",
        "TransSensit",
        "TransValue",
        "Trans",
        "Location",
        "Delta",
        "IncrMean",
        "IncrSensit",
        "IncrValue",
        "Incr",
        "PathMean",
        "PathSensit",
        "PathValue",
        "Path",
        "trigger_edge",
    ]
    skip_first_rows = 2
    default_attrs_by_type = {
        "net": ["Fanout"],
        "input_pin": [
            "Derate",
            "DerateA",
            "DerateB",
            "Cap",
            "D-Trans",
            "TransMean",
            "TransSensit",
            "TransValue",
            "Trans",
            "Location",
            "Delta",
            "IncrMean",
            "IncrSensit",
            "IncrValue",
            "Incr",
            "PathMean",
            "PathSensit",
            "PathValue",
            "Path",
            "trigger_edge",
        ],
        "output_pin": [
            "Derate",
            "DerateA",
            "DerateB",
            "Cap",
            "D-Trans",
            "TransMean",
            "TransSensit",
            "TransValue",
            "Trans",
            "Location",
            "Delta",
            "IncrMean",
            "IncrSensit",
            "IncrValue",
            "Incr",
            "PathMean",
            "PathSensit",
            "PathValue",
            "Path",
            "trigger_edge",
        ],
    }

    _output_pin_names = frozenset({"Q", "Z", "ZN", "ZP"})

    _re_startpoint = re.compile(r"^\s*Startpoint:\s+(.+?)\s+\(.+\)\s*$")
    _re_endpoint = re.compile(r"^\s*Endpoint:\s+(.+?)\s+\(.+\)\s*$")
    _re_clocked_by = re.compile(r"clocked by ([^\s)]+)")
    _re_slack = re.compile(r"^\s*slack\s+\((VIOLATED|MET)\)(?:\s|$)")
    _re_slack_value = re.compile(r"(-?\d+\.\d+)\s*$")
    _re_last_common_pin = re.compile(
        r"^\s*Last\s+common\s+pin\s*[:=]\s*(.+?)\s*$", re.IGNORECASE
    )
    _re_last_common_pin2 = re.compile(r"^\s*Last\s+common\s+pin\s+(.+?)\s*$", re.IGNORECASE)
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
        table_info, table_start = self._findTableStart(lines)
        self._parseLaunchSegment(lines, meta, table_info, table_start, launch_rows)
        self._parseCaptureSegment(lines, meta, table_info, table_start, capture_rows)
        self._fillRequiredAndArrival(lines, meta)
        self._fillUncertainty(lines, meta)

        #         ast_common_pin/common_pin_delay/clock_period
        #      ommon_pin_delay = Path(common)  lock_period = capture       ?clock  ?Incr
        if not meta.get("last_common_pin"):
            #     header  ?Last common pin     ?slack                   
            for line in lines:
                m_lcp = self._re_last_common_pin.match(line) or self._re_last_common_pin2.match(line)
                if m_lcp:
                    meta["last_common_pin"] = m_lcp.group(1).strip()
                    break

        # fallback          ?last_common_pin    ?startpoint    
        if not meta.get("last_common_pin"):
            meta["last_common_pin"] = meta.get("startpoint", "")

        lcp_norm = self._normalizePin(meta.get("last_common_pin", ""))
        metric_key = "Path"

        def _findCommonPinDelay(rows: list[dict[str, Any]]) -> str:
            for r in rows:
                p_norm = self._normalizePin(r.get("point", "") or "")
                if lcp_norm and p_norm == lcp_norm:
                    return str(r.get(metric_key, "") or "")
            return ""

        meta["common_pin_delay"] = _findCommonPinDelay(capture_rows) or _findCommonPinDelay(launch_rows) or ""

        # capture                  Incr     clock_period
        clock_period = ""
        for r in capture_rows:
            val = str(r.get("Incr", "") or "").strip()
            if val:
                clock_period = val
                break
        meta["clock_period"] = clock_period

        return meta, launch_rows, capture_rows

    @staticmethod
    def _defaultMeta(path_id: int) -> dict[str, Any]:
        """    ?path     ?meta     """
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
            # Last common pin                   ?
            "last_common_pin": "",
            # common pin            T/format1  ?Path ?
            "common_pin_delay": "",
            # capture       ?clock          PT/format1  ?Incr ?
            "clock_period": "",
            "uncertainty": "",
        }

    def _fillMetaFromHeader(self, lines: list[str], meta: dict[str, Any]) -> None:
        """ ?path           Startpoint/Endpoint/slack     ?meta """
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

    def _findTableStart(self, lines: list[str]) -> tuple[dict[str, Any], int]:
        """定位经典/LVF 点表头，返回表格模式与数据起始行。"""
        lvf_info, lvf_start = self._findLvfTableStart(lines)
        if lvf_info:
            return lvf_info, lvf_start
        classic_info, classic_start = self._findClassicTableStart(lines)
        return classic_info, classic_start

    def _findClassicTableStart(self, lines: list[str]) -> tuple[dict[str, Any], int]:
        """定位传统 format1 表头。"""
        col_pos: dict[str, int] = {}
        table_start = 0
        classic_attrs = ["Fanout", "Derate", "Cap", "Trans", "Location", "Incr", "Path"]
        for idx, line in enumerate(lines):
            if self._re_point_header.match(line):
                col_pos = self.extractColumnPositions(line, classic_attrs)
                if "Location" in col_pos:
                    table_start = idx + 1
                    if table_start < len(lines) and self._re_sep_line.match(lines[table_start]):
                        table_start += 1
                    return {"mode": "classic", "col_pos": col_pos}, table_start
        return {"mode": "classic", "col_pos": {}}, table_start

    def _findLvfTableStart(self, lines: list[str]) -> tuple[dict[str, Any], int]:
        """定位 LVF 双层表头（支持“分组行在上、属性行在下”的正确格式）。"""
        for idx in range(len(lines) - 1):
            line_a = lines[idx]
            line_b = lines[idx + 1]

            # 正确格式：上一行是 Trans/Incr/Path 分组，下一行是 Fanout/Derate/.../Mean/Sensit/Value
            if self._isLvfGroupHeaderLine(line_a) and self._isLvfAttrHeaderLine(line_b):
                col_pos = self._buildLvfColumnPositions(line_b)
                if col_pos:
                    table_start = idx + 2
                    if table_start < len(lines) and self._re_sep_line.match(lines[table_start]):
                        table_start += 1
                    return {"mode": "lvf", "col_pos": col_pos}, table_start

            # 兼容历史反向格式：属性行在上、分组行在下
            if self._isLvfAttrHeaderLine(line_a) and self._isLvfGroupHeaderLine(line_b):
                col_pos = self._buildLvfColumnPositions(line_a)
                if col_pos:
                    table_start = idx + 2
                    if table_start < len(lines) and self._re_sep_line.match(lines[table_start]):
                        table_start += 1
                    return {"mode": "lvf", "col_pos": col_pos}, table_start
        return {}, 0

    @staticmethod
    def _isLvfGroupHeaderLine(line: str) -> bool:
        text = (line or "").lower()
        return ("trans" in text) and ("incr" in text) and ("path" in text)

    @staticmethod
    def _isLvfAttrHeaderLine(line: str) -> bool:
        text = (line or "").lower()
        if "fanout" not in text or "derate" not in text or "cap" not in text:
            return False
        return text.count("mean") >= 3 and text.count("sensit") >= 3 and text.count("value") >= 3

    def _buildLvfColumnPositions(self, attr_line: str) -> dict[str, int]:
        """根据 LVF 属性行构建固定列宽起始位置。"""
        col_pos: dict[str, int] = {}
        for src, dst in [
            ("Fanout", "Fanout"),
            ("Derate", "Derate"),
            ("Cap", "Cap"),
            ("DTrans", "D-Trans"),
            ("Location", "Location"),
            ("Delta", "Delta"),
        ]:
            idx = attr_line.find(src)
            if idx >= 0:
                col_pos[dst] = idx

        means = [m.start() for m in re.finditer(r"Mean", attr_line)]
        sensits = [m.start() for m in re.finditer(r"Sensit", attr_line)]
        values = [m.start() for m in re.finditer(r"Value", attr_line)]
        if min(len(means), len(sensits), len(values)) < 3:
            return {}
        groups = ["Trans", "Incr", "Path"]
        for i, group in enumerate(groups):
            col_pos[f"{group}Mean"] = means[i]
            col_pos[f"{group}Sensit"] = sensits[i]
            col_pos[f"{group}Value"] = values[i]
        return col_pos

    def _parseByPositions(self, line: str, col_pos: dict[str, int]) -> tuple[str, dict[str, str]]:
        """按列起始位置切分单行。"""
        content = line.rstrip()
        ordered = sorted(col_pos.items(), key=lambda item: item[1])
        if not ordered:
            return "", {}
        point = content[: ordered[0][1]].strip()
        attrs: dict[str, str] = {}
        for i, (name, start) in enumerate(ordered):
            end = ordered[i + 1][1] if i + 1 < len(ordered) else len(content)
            value = content[start:end].strip() if start < end else ""
            attrs[name] = "" if value == "-" else value
        return point, attrs

    @staticmethod
    def _splitDerateValues(value: str) -> tuple[str, str]:
        """拆分 LVF Derate 双值（a:b）；单值则仅返回第一个。"""
        text = str(value or "").strip()
        if not text:
            return "", ""
        if ":" not in text:
            return text, ""
        left, right = text.split(":", 1)
        return left.strip(), right.strip()

    def _parsePointAttrs(self, line: str, table_info: dict[str, Any], row_kind: str) -> tuple[str, Dict[str, str]]:
        """按表格模式解析单行属性，并对 LVF 字段做兼容回填。"""
        mode = str((table_info or {}).get("mode") or "classic")
        col_pos = dict((table_info or {}).get("col_pos") or {})
        if mode == "lvf":
            point, raw_attrs = self._parseByPositions(line, col_pos)
            attrs: Dict[str, str] = {name: "" for name in self.attrs_order}
            for key in ("Fanout", "Derate", "Cap", "D-Trans", "Location", "Delta"):
                attrs[key] = raw_attrs.get(key, "")
            for key in (
                "TransMean",
                "TransSensit",
                "TransValue",
                "IncrMean",
                "IncrSensit",
                "IncrValue",
                "PathMean",
                "PathSensit",
                "PathValue",
            ):
                attrs[key] = raw_attrs.get(key, "")
            attrs["Trans"] = attrs["TransValue"]
            attrs["Incr"] = attrs["IncrValue"]
            attrs["Path"] = attrs["PathValue"]
            attrs["DerateA"], attrs["DerateB"] = self._splitDerateValues(attrs["Derate"])
            return point, attrs

        point, attrs = self.parseFixedWidthAttrs(line, col_pos, ["Fanout", "Derate", "Cap", "Trans", "Location", "Incr", "Path"])
        merged: Dict[str, str] = {name: "" for name in self.attrs_order}
        for key, value in attrs.items():
            merged[key] = value
        if not row_kind:
            if self._re_clock_start.match(line):
                row_kind = "clock"
            elif "(net)" in point:
                row_kind = "net"
            else:
                row_kind = "pin"
        smart_numeric = self._parseNumericColumns(line, col_pos, row_kind)
        if smart_numeric:
            for col, val in smart_numeric.items():
                if val:
                    merged[col] = val
        merged["DerateA"], merged["DerateB"] = self._splitDerateValues(merged.get("Derate", ""))
        return point, merged

    def _classify_row_kind(
        self,
        point: str,
        line: str,
        segment_row_index: int,
        in_launch: bool,
    ) -> str:
        """
                  point                 ?
        - clock: clock  ?
        - net:    ?(net)    
        - pin:       pin  ?
                                   ?
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
        """  row_kind         Incr/Path         """
        if not row_kind:
            return None
        tokens = re.findall(r"-?\d+(?:\.\d+)?", line)
        if not tokens:
            return None

        attrs: Dict[str, str] = {name: "" for name in self.attrs_order}
        layout_attrs = self._layout_runtime.extractRowKindNumeric(row_kind, line)
        if layout_attrs:
            for col, val in layout_attrs.items():
                if col in attrs and val:
                    attrs[col] = val
            return attrs

        if row_kind in ("clock", "net", "pin"):
            if len(tokens) >= 2:
                attrs["Incr"] = tokens[-2]
                attrs["Path"] = tokens[-1]
            elif len(tokens) == 1:
                attrs["Path"] = tokens[-1]
            return attrs

        return attrs

    def _parseLaunchSegment(
        self,
        lines: list[str],
        meta: dict[str, Any],
        table_info: dict[str, Any],
        table_start: int,
        launch_rows: list[dict[str, Any]],
    ) -> None:
        """          launch     ?clock     data arrival time     """
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
                    row_kind = self._classify_row_kind(
                        "", lines[k], k - launch_start_idx, in_launch=True
                    )
                    raw_point, attrs = self._parsePointAttrs(lines[k], table_info, row_kind)
                    if not raw_point:
                        continue
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
        table_info: dict[str, Any],
        table_start: int,
        capture_rows: list[dict[str, Any]],
    ) -> None:
        """          capture    data arrival     ?clock     library setup     """
        after_data_arrival = False
        in_capture = False
        capture_start_idx = -1
        for j in range(table_start, len(lines)):
            line = lines[j]
            if self._re_data_arrival.match(line):
                after_data_arrival = True
                continue
            if after_data_arrival and (not in_capture) and self._re_clock_start.match(line):
                in_capture = True
                capture_start_idx = j
                continue
            if in_capture and self._re_library_setup.match(line):
                for k in range(capture_start_idx, j):
                    row_kind = self._classify_row_kind(
                        "", lines[k], k - capture_start_idx, in_launch=False
                    )
                    raw_point, attrs = self._parsePointAttrs(lines[k], table_info, row_kind)
                    if not raw_point:
                        continue
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
        """          ?data required time / data arrival time            """
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
        """ ?Path        ?r/f     trigger_edge    ?Path           """
        path_val = str(attrs.get("Path", "") or "").strip()
        if not path_val:
            attrs["trigger_edge"] = ""
            return attrs
        tokens = path_val.split()
        if tokens and tokens[-1] in ("r", "f"):
            edge = tokens[-1]
            attrs["trigger_edge"] = edge
            attrs["Path"] = " ".join(tokens[:-1])
            if "PathValue" in attrs:
                attrs["PathValue"] = attrs["Path"]
        else:
            attrs.setdefault("trigger_edge", "")
        return attrs

    @staticmethod
    def _extractTriggerEdgeFromLine(line: str) -> str:
        """          ?trigger_edge  /f   """
        m = re.search(r"\s([rf])\s*$", line.strip(), re.IGNORECASE)
        return m.group(1).lower() if m else ""

    def _inferPointType(self, point_name: str) -> str:
        """    point            et / output_pin / input_pin """
        if not point_name or "(net)" in point_name:
            return "net"
        m = re.search(r"/([A-Za-z0-9_\[\]]+)\s*\(?[A-Z]?", point_name)
        pin = m.group(1) if m else ""
        if pin in self._output_pin_names:
            return "output_pin"
        return "input_pin"








