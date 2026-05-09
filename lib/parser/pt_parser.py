"""
PT（PrimeTime 风格）Timing 报告解析器。

继承 Format1Parser，覆盖表头与正则以匹配 PT 的 Startpoint/Endpoint、Mean/Sensit 列及
library setup/hold 行等差异。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from .format1_parser import Format1Parser
from .layout_runtime import LayoutRuntime


PT_FLOAT_COLS = ("Cap", "DTrans", "Trans", "Derate", "Delta", "Incr", "Path", "Voltage")
PT_FANOUT_COL = "Fanout"


def _format_pt_metric_for_csv(col: str, val: Any) -> Any:
    """PT 抽取 CSV：Fanout 整数，关键浮点列保留 4 位小数。"""
    if val is None or val == "":
        return "" if col in PT_FLOAT_COLS or col == PT_FANOUT_COL else val
    if col == PT_FANOUT_COL:
        try:
            return int(float(str(val).strip().split()[0] if isinstance(val, str) else val))
        except (ValueError, TypeError):
            return val
    if col in PT_FLOAT_COLS:
        try:
            s = str(val).replace("&", "").strip()
            #        ?r/f
            for suffix in (" r", " f"):
                if s.endswith(suffix):
                    s = s[:-2].strip()
                    break
            return f"{float(s):.4f}"
        except (ValueError, TypeError):
            return val
    return val


class PtParser(Format1Parser):
    """PT 报告解析器。"""

    def __init__(self, attrs_order: list[str] | None = None, attrs_by_type: dict[str, list[str]] | None = None) -> None:
        super().__init__(attrs_order, attrs_by_type)
        self._layout_runtime = LayoutRuntime("pt")

    default_attrs_order = ["Fanout", "Cap", "DTrans", "Trans", "Derate", "Delta", "Incr", "Path", "Voltage", "trigger_edge"]
    skip_first_rows = 2
    default_attrs_by_type = {
        "net": ["Fanout", "Cap"],
        "input_pin": ["DTrans", "Trans", "Derate", "Delta", "Incr", "Path", "Voltage", "trigger_edge"],
        # PT 语义：Delta 仅出现在 input pin；报告里 output 行可能仍有占位列，解析时跳过以免 Incr/Path 错位。
        "output_pin": ["DTrans", "Trans", "Derate", "Incr", "Path", "Voltage", "trigger_edge"],
    }

    _re_startpoint = re.compile(r"^\s+Startpoint:\s+(.+?)\s*$")
    _re_endpoint = re.compile(r"^\s+Endpoint:\s+(.+?)\s*$")
    _re_clocked_by = re.compile(r"clocked by ([^\s)]+)")
    _re_slack = re.compile(r"^\s*(?:slack\s+\((VIOLATED|MET)\)|.*\bslack\s+\((VIOLATED|MET)\))", re.IGNORECASE)
    _re_slack_value = re.compile(r"(-?\d+\.\d+)\s*$")
    _re_last_common_pin = re.compile(
        r"^\s*Last\s+common\s+pin\s*[:=]\s*(.+?)\s*$", re.IGNORECASE
    )
    _re_last_common_pin2 = re.compile(
        r"^\s*Last\s+common\s+pin\s+(.+?)\s*$", re.IGNORECASE
    )
    _re_point_header = re.compile(r"^\s+(?:Point\s+|Fanout\s+)", re.IGNORECASE)
    _re_sep_line = re.compile(r"^\s+-{3,}\s*$")
    _re_clock_rise = re.compile(r"clock\s+\S+\s+\(rise\s+edge\)", re.IGNORECASE)
    _re_data_arrival = re.compile(r"data\s+arrival\s+time", re.IGNORECASE)
    _re_library_setup = re.compile(r"library\s+(setup|hold)\s+time", re.IGNORECASE)
    _re_capture_tail = re.compile(
        r"(clock reconvergence pessimism|clock uncertainty|library\s+(setup|hold)\s+time)",
        re.IGNORECASE,
    )

    @staticmethod
    def _parsePtLineByColumns(line: str, col_pos: dict[str, int], attrs_order: list[str]) -> tuple[str, dict[str, str]]:
        """提取 PT point 文本；字段值由 token 语义解析，避免固定列截断。"""
        content = line.rstrip()
        attrs: dict[str, str] = {name: "" for name in attrs_order}
        if not content.strip():
            return "", attrs
        if "Point" in col_pos:
            point_start = col_pos["Point"]
            metric_positions = [
                pos for name, pos in col_pos.items() if name != "Point" and name in attrs_order
            ]
            if metric_positions and point_start > min(metric_positions):
                point = PtParser._extractPointLastText(content)
                return point, attrs
            fields = Format1Parser._splitByFieldGaps(content)
            point = fields[0] if fields else ""
            return point, attrs
        fields = Format1Parser._splitByFieldGaps(content)
        return (fields[0] if fields else ""), attrs

    @staticmethod
    def _isPointLastLayout(col_pos: dict[str, int]) -> bool:
        """判断 PT 表格是否为数值列在前、Point 在末尾。"""
        if "Point" not in col_pos:
            return False
        point_start = col_pos["Point"]
        metric_positions = [pos for name, pos in col_pos.items() if name != "Point"]
        return bool(metric_positions and point_start > min(metric_positions))

    @staticmethod
    def _extractPointLastText(line: str) -> str:
        """Point 尾列版式：取最后一个数值 token 之后的文本作为 point。"""
        tokens = (line or "").strip().split()
        last_numeric_idx = -1
        for idx, token in enumerate(tokens):
            if re.fullmatch(r"-?\d+(?:\.\d+)?", token):
                last_numeric_idx = idx
        if last_numeric_idx < 0:
            return ""
        point_start = last_numeric_idx + 1
        if point_start < len(tokens) and tokens[point_start].lower() in ("r", "f"):
            point_start += 1
        return " ".join(tokens[point_start:]).strip()

    @staticmethod
    def _metricTextWithoutPoint(line: str, col_pos: dict[str, int]) -> str:
        """去掉 point 文本后再提取数值，防止实例名中的数字污染字段。"""
        content = line or ""
        if PtParser._isPointLastLayout(col_pos):
            tokens = content.strip().split()
            last_numeric_idx = -1
            for idx, token in enumerate(tokens):
                if re.fullmatch(r"-?\d+(?:\.\d+)?", token):
                    last_numeric_idx = idx
            if last_numeric_idx >= 0:
                return " ".join(tokens[: last_numeric_idx + 1])
            return ""

        fields = Format1Parser._splitByFieldGaps(content)
        if len(fields) > 1:
            return " ".join(fields[1:])
        return content

    @staticmethod
    def _mergeAttrsPreferFixedWidth(
        base_attrs: dict[str, str],
        fallback_attrs: dict[str, str] | None,
        attrs_order: list[str],
    ) -> dict[str, str]:
        """合并解析结果：固定列宽值优先，fallback 只补空。"""
        attrs = {name: base_attrs.get(name, "") for name in attrs_order}
        if not fallback_attrs:
            return attrs
        for name, value in fallback_attrs.items():
            if name in attrs and value and not attrs.get(name):
                attrs[name] = value
        return attrs

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
            # Last common pin                   ?
            "last_common_pin": "",
            # common pin            T/format1  ?Path ?
            "common_pin_delay": "",
            # capture       ?clock          PT/format1  ?Incr ?
            "clock_period": "",
            "uncertainty": "",
        }
        launch_rows: list[dict[str, Any]] = []
        capture_rows: list[dict[str, Any]] = []

        for i, line in enumerate(lines):
            m = self._re_startpoint.match(line)
            if m:
                meta["startpoint"] = m.group(1).strip()
                cm = self._re_clocked_by.search(line)
                if not cm and i + 1 < len(lines):
                    cm = self._re_clocked_by.search(lines[i + 1])
                meta["startpoint_clock"] = cm.group(1).strip() if cm else ""
                continue
            m = self._re_endpoint.match(line)
            if m:
                meta["endpoint"] = m.group(1).strip()
                cm = self._re_clocked_by.search(line)
                if not cm and i + 1 < len(lines):
                    cm = self._re_clocked_by.search(lines[i + 1])
                meta["endpoint_clock"] = cm.group(1).strip() if cm else ""
                continue
            slack_status = self._extractSlackStatus(line)
            if slack_status:
                meta["slack_status"] = slack_status
                meta["slack"] = self._extractPathMetric(line, {})
                break

        #     Last common pin     slack                   
        if not meta.get("last_common_pin"):
            for line in lines:
                m_lcp = self._re_last_common_pin.match(line) or self._re_last_common_pin2.match(line)
                if m_lcp:
                    meta["last_common_pin"] = m_lcp.group(1).strip()
                    break

        col_pos: dict[str, int] = {}
        table_start = 0
        for idx, line in enumerate(lines):
            if self._re_point_header.match(line) and ("Point" in line or ("Fanout" in line and "Path" in line)):
                col_pos = self.extractColumnPositions(line, self.attrs_order + ["Point"])
                if "Path" in col_pos:
                    table_start = idx + 1
                    if table_start < len(lines) and self._re_sep_line.match(lines[table_start]):
                        table_start += 1
                    break
                col_pos = {}

        in_launch = False
        launch_start_idx = -1
        for j in range(table_start, len(lines)):
            if self._re_clock_rise.search(lines[j]):
                in_launch = True
                launch_start_idx = j
                continue
            if in_launch and self._re_data_arrival.search(lines[j]):
                for k in range(launch_start_idx, j + 1):
                    raw_point, base_attrs = self._parsePtLineByColumns(lines[k], col_pos, self.attrs_order)
                    if not raw_point:
                        continue
                    row_kind = self._classify_row_kind(raw_point, lines[k], k - launch_start_idx, True)
                    pin_ptype = self._inferPointType(raw_point) if row_kind == "pin" else ""
                    smart_attrs = self._parseNumericColumns(lines[k], col_pos, row_kind, pin_ptype)
                    attrs = self._mergeAttrsPreferFixedWidth(
                        base_attrs, smart_attrs, self.attrs_order
                    )
                    ptype = self._inferPointType(raw_point)
                    if ptype in ("input_pin", "output_pin"):
                        attrs = self._extractTriggerEdgeFromPath(attrs)
                        if not attrs.get("trigger_edge"):
                            attrs["trigger_edge"] = self._extractTriggerEdgeFromLine(lines[k])
                    filtered = self.applyTypeFilter(attrs, ptype, k - launch_start_idx)
                    launch_rows.append(self.buildPointRow(meta, len(launch_rows) + 1, raw_point, filtered))
                metric = self._extractPathMetric(lines[j], col_pos)
                if metric:
                    meta["arrival_time"] = metric
                break

        after_data_arrival = False
        in_capture = False
        capture_start_idx = -1
        for j in range(table_start, len(lines)):
            if self._re_data_arrival.search(lines[j]):
                after_data_arrival = True
                continue
            if after_data_arrival and self._re_clock_rise.search(lines[j]):
                in_capture = True
                capture_start_idx = j
                continue
            if in_capture and self._re_capture_tail.search(lines[j]):
                for k in range(capture_start_idx, j):
                    raw_point, base_attrs = self._parsePtLineByColumns(lines[k], col_pos, self.attrs_order)
                    if not raw_point:
                        continue
                    row_kind = self._classify_row_kind(raw_point, lines[k], k - capture_start_idx, True)
                    pin_ptype = self._inferPointType(raw_point) if row_kind == "pin" else ""
                    smart_attrs = self._parseNumericColumns(lines[k], col_pos, row_kind, pin_ptype)
                    attrs = self._mergeAttrsPreferFixedWidth(
                        base_attrs, smart_attrs, self.attrs_order
                    )
                    ptype = self._inferPointType(raw_point)
                    if ptype in ("input_pin", "output_pin"):
                        attrs = self._extractTriggerEdgeFromPath(attrs)
                        if not attrs.get("trigger_edge"):
                            attrs["trigger_edge"] = self._extractTriggerEdgeFromLine(lines[k])
                    filtered = self.applyTypeFilter(attrs, ptype, k - capture_start_idx)
                    capture_rows.append(self.buildPointRow(meta, len(capture_rows) + 1, raw_point, filtered))
                break

        for line in lines:
            if "data required time" in line:
                metric = self._extractPathMetric(line, col_pos)
                if metric:
                    meta["required_time"] = metric
                    break

        if not meta["arrival_time"]:
            for line in lines:
                if "data arrival time" in line:
                    metric = self._extractPathMetric(line, col_pos)
                    if metric:
                        meta["arrival_time"] = metric
                        break

        self._fillUncertainty(lines, meta)

        #         ast_common_pin/common_pin_delay/clock_period
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

        clock_period = ""
        for r in capture_rows:
            val = str(r.get("Incr", "") or "").strip()
            if val:
                clock_period = val
                break
        meta["clock_period"] = clock_period

        return meta, launch_rows, capture_rows

    @staticmethod
    def _extractSlackStatus(line: str) -> str:
        """从 PT slack 行中提取 MET/VIOLATED，兼容 label 位于行首或 Point 尾列。"""
        m = re.search(r"\bslack\s+\((VIOLATED|MET)\)", line, re.IGNORECASE)
        return m.group(1).upper() if m else ""

    def _extractPathMetric(self, line: str, col_pos: dict[str, int]) -> str:
        """
        从 PT summary 行提取指标值。

        不按 Path 列位置切片：summary 行本身不含实例名，直接取行内最后一个数值即可兼容
        “label 在前”和“label 在 Point 尾列”两种版式。
        """
        vm = re.findall(r"-?\d+(?:\.\d+)?", line)
        return vm[-1] if vm else ""

    def _classify_row_kind(self, point: str, line: str, segment_row_index: int, in_launch: bool) -> str:
        """
                                    ?row_kind ?
        - clock:           launch/capture        ?clock  ?
        - clock_src_lat:   clock source latency  ?
        - net:              ?(net)    
        - pin:                 pin  ?
                                       ?
        """
        if self._re_clock_rise.search(line):
            return "clock"
        if "clock source latency" in line:
            return "clock_src_lat"
        if "(net)" in point:
            return "net"
        if in_launch and segment_row_index >= 0:
            return "pin"
        return ""

    def _parseNumericColumns(
        self,
        line: str,
        col_pos: dict[str, int],
        row_kind: str,
        pin_ptype: str = "",
    ) -> Dict[str, str] | None:
        """PT                  net        """
        if not row_kind:
            return None

        expected_by_kind: Dict[str, List[str]] = {
            "clock": ["Delta", "Incr", "Path"],
            "clock_src_lat": ["Delta", "Incr", "Path"],
            "net": ["Fanout", "Cap", "Incr", "Path"],
            "pin": ["DTrans", "Trans", "Derate", "Delta", "Incr", "Path", "Voltage"],
        }
        expected = expected_by_kind.get(row_kind)
        if not expected:
            return None

        if row_kind == "net":
            attrs: Dict[str, str] = {name: "" for name in self.attrs_order}
            metric_text = self._metricTextWithoutPoint(line, col_pos)
            nums = re.findall(r"-?\d+(?:\.\d+)?", metric_text)
            if not nums:
                return None
            if len(nums) >= 4:
                tail = nums[-4:]
                for i, name in enumerate(expected):
                    attrs[name] = tail[i]
            elif len(nums) >= 2:
                attrs["Fanout"] = nums[0]
                attrs["Cap"] = nums[1]
            return attrs

        metric_text = self._metricTextWithoutPoint(line, col_pos)
        tokens_iter = list(re.finditer(r"-?\d+(?:\.\d+)?", metric_text))
        if not tokens_iter:
            return None
        tokens = [m.group(0) for m in tokens_iter]

        attrs = {name: "" for name in self.attrs_order}
        if row_kind == "pin" and pin_ptype == "output_pin":
            # 与 input 相同 token 数时第 4 个数为 Delta 占位，不参与 output 字段映射。
            if len(tokens) >= 7:
                seg = tokens[-7:]
                attrs["DTrans"] = seg[0]
                attrs["Trans"] = seg[1]
                attrs["Derate"] = seg[2]
                attrs["Incr"] = seg[4]
                attrs["Path"] = seg[5]
                attrs["Voltage"] = seg[6]
            else:
                out_expected = ["DTrans", "Trans", "Derate", "Incr", "Path", "Voltage"]
                limit = min(len(tokens), len(out_expected))
                tail = tokens[-limit:] if limit else []
                for i, name in enumerate(out_expected[:limit]):
                    attrs[name] = tail[i]
        else:
            limit = min(len(tokens), len(expected))
            tail = tokens[-limit:] if limit else []
            for i, name in enumerate(expected[:limit]):
                attrs[name] = tail[i]
        if row_kind == "pin":
            edge_match = re.search(
                r"-?\d+(?:\.\d+)?\s*&?\s+([rf])\s+-?\d+(?:\.\d+)?\s*$",
                metric_text.strip(),
                re.IGNORECASE,
            )
            if edge_match:
                attrs["trigger_edge"] = edge_match.group(1).lower()
        return attrs

    def buildPointRow(
        self,
        meta: dict[str, Any],
        point_index: int,
        point: str,
        attrs: dict[str, Any],
    ) -> dict[str, Any]:
        """PT 行清洗：去掉 Incr 的 '&'，并统一数值精度。"""
        row = super().buildPointRow(meta, point_index, point, attrs)
        incr = row.get("Incr", "")
        if isinstance(incr, str) and "&" in incr:
            row["Incr"] = incr.replace("&", "").strip()
        for col in [PT_FANOUT_COL] + list(PT_FLOAT_COLS):
            if col in row and row[col] not in (None, ""):
                row[col] = _format_pt_metric_for_csv(col, row[col])
        return row








