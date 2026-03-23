"""
PT（PrimeTime 风格）Timing 报告解析器。

继承 Format1Parser，覆盖表头与正则以匹配 PT 的 Startpoint/Endpoint（无括号类型）、
Mean/Sensit 列及 library setup/hold 行。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from .format1_parser import Format1Parser


PT_FLOAT_COLS = ("Cap", "Trans", "Derate", "Mean", "Sensit", "Incr", "Path")
PT_FANOUT_COL = "Fanout"


def _format_pt_metric_for_csv(col: str, val: Any) -> Any:
    """PT 抽取 CSV：Fanout 整数，Cap/Trans/Derate/Mean/Sensit/Incr/Path 保留 4 位小数。"""
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
            # 去掉末尾的 r/f
            for suffix in (" r", " f"):
                if s.endswith(suffix):
                    s = s[:-2].strip()
                    break
            return f"{float(s):.4f}"
        except (ValueError, TypeError):
            return val
    return val


class PtParser(Format1Parser):
    """PT 报告解析器。表头含 Point, Fanout, Cap, Trans, Derate, Mean, Sensit, Incr, Path；Startpoint/Endpoint 可为实例名。"""

    default_attrs_order = ["Fanout", "Cap", "Trans", "Derate", "Mean", "Sensit", "Incr", "Path", "trigger_edge"]
    skip_first_rows = 2
    default_attrs_by_type = {
        "net": ["Fanout", "Cap"],
        "input_pin": ["Trans", "Derate", "Mean", "Sensit", "Incr", "Path", "trigger_edge"],
        "output_pin": ["Trans", "Derate", "Mean", "Sensit", "Incr", "Path", "trigger_edge"],
    }

    _re_startpoint = re.compile(r"^\s+Startpoint:\s+(.+?)\s*$")
    _re_endpoint = re.compile(r"^\s+Endpoint:\s+(.+?)\s*$")
    _re_clocked_by = re.compile(r"clocked by ([^\s)]+)")
    _re_slack = re.compile(r"^\s+slack\s+\((VIOLATED|MET)\)\s")
    _re_slack_value = re.compile(r"(-?\d+\.\d+)\s*$")
    _re_last_common_pin = re.compile(
        r"^\s*Last\s+common\s+pin\s*[:=]\s*(.+?)\s*$", re.IGNORECASE
    )
    _re_last_common_pin2 = re.compile(
        r"^\s*Last\s+common\s+pin\s+(.+?)\s*$", re.IGNORECASE
    )
    _re_point_header = re.compile(r"^\s+Point\s+", re.IGNORECASE)
    _re_sep_line = re.compile(r"^\s+-{3,}\s*$")
    _re_clock_rise = re.compile(r"^\s+clock\s+\S+\s+\(rise\s+edge\)\s")
    _re_data_arrival = re.compile(r"^\s+data\s+arrival\s+time\s")
    _re_library_setup = re.compile(r"^\s+library\s+(setup|hold)\s+time\s")
    _re_capture_tail = re.compile(
        r"^\s+(clock reconvergence pessimism|clock uncertainty|library\s+(setup|hold)\s+time)\s",
        re.IGNORECASE,
    )

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
            # Last common pin（公共点概念）相关派生字段
            "last_common_pin": "",
            # common pin 处的累计延迟（PT/format1 用 Path）
            "common_pin_delay": "",
            # capture 侧第一行 clock 的周期度量（PT/format1 用 Incr）
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
            m = self._re_slack.match(line)
            if m:
                meta["slack_status"] = m.group(1).strip()
                vm = self._re_slack_value.search(line)
                meta["slack"] = vm.group(1).strip() if vm else ""
                break

        # 兼容 Last common pin 行在 slack 之后才出现：全局扫描兜底
        if not meta.get("last_common_pin"):
            for line in lines:
                m_lcp = self._re_last_common_pin.match(line) or self._re_last_common_pin2.match(line)
                if m_lcp:
                    meta["last_common_pin"] = m_lcp.group(1).strip()
                    break

        col_pos: dict[str, int] = {}
        table_start = 0
        for idx, line in enumerate(lines):
            if self._re_point_header.match(line):
                col_pos = self.extractColumnPositions(line, self.attrs_order)
                if "Path" in col_pos:
                    table_start = idx + 1
                    if table_start < len(lines) and self._re_sep_line.match(lines[table_start]):
                        table_start += 1
                    break
                col_pos = {}

        in_launch = False
        launch_start_idx = -1
        for j in range(table_start, len(lines)):
            if self._re_clock_rise.match(lines[j]):
                in_launch = True
                launch_start_idx = j
                continue
            if in_launch and self._re_data_arrival.match(lines[j]):
                for k in range(launch_start_idx, j + 1):
                    raw_point, base_attrs = self.parseFixedWidthAttrs(lines[k], col_pos, self.attrs_order)
                    if not raw_point:
                        continue
                    row_kind = self._classify_row_kind(raw_point, lines[k], k - launch_start_idx, True)
                    smart_attrs = self._parseNumericColumns(lines[k], col_pos, row_kind)
                    attrs = smart_attrs or base_attrs
                    ptype = self._inferPointType(raw_point)
                    if ptype in ("input_pin", "output_pin"):
                        attrs = self._extractTriggerEdgeFromPath(attrs)
                        if not attrs.get("trigger_edge"):
                            attrs["trigger_edge"] = self._extractTriggerEdgeFromLine(lines[k])
                    filtered = self.applyTypeFilter(attrs, ptype, k - launch_start_idx)
                    launch_rows.append(self.buildPointRow(meta, len(launch_rows) + 1, raw_point, filtered))
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
            if after_data_arrival and self._re_clock_rise.match(lines[j]):
                in_capture = True
                capture_start_idx = j
                continue
            if in_capture and self._re_capture_tail.match(lines[j]):
                for k in range(capture_start_idx, j):
                    raw_point, base_attrs = self.parseFixedWidthAttrs(lines[k], col_pos, self.attrs_order)
                    if not raw_point:
                        continue
                    row_kind = self._classify_row_kind(raw_point, lines[k], k - capture_start_idx, True)
                    smart_attrs = self._parseNumericColumns(lines[k], col_pos, row_kind)
                    attrs = smart_attrs or base_attrs
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

        self._fillUncertainty(lines, meta)

        # 派生字段：last_common_pin/common_pin_delay/clock_period
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

    def _classify_row_kind(self, point: str, line: str, segment_row_index: int, in_launch: bool) -> str:
        """
        根据行内容与推断类型，返回当前点表行的 row_kind：
        - clock:           launch/capture 段的第一行 clock 行
        - clock_src_lat:   clock source latency 行
        - net:             含 (net) 的行
        - pin:             其余 pin 行
        其他行返回空串，表示使用原始定宽解析结果。
        """
        if self._re_clock_rise.match(line):
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
    ) -> Dict[str, str] | None:
        """
        基于 row_kind + 数值 token 顺序解析当前行的数值列。

        若无法可靠映射（无数字或 row_kind 未知），返回 None，调用方应回退到 parseFixedWidthAttrs 的 attrs。
        """
        # 行类型未知时不启用数值映射；不再依赖列起始位置，仅看整行数值顺序
        if not row_kind:
            return None
        expected_by_kind: Dict[str, List[str]] = {
            "clock": ["Mean", "Incr", "Path"],
            "clock_src_lat": ["Mean", "Sensit", "Incr", "Path"],
            "net": ["Fanout", "Cap", "Incr", "Path"],
            "pin": ["Trans", "Derate", "Mean", "Sensit", "Incr", "Path"],
        }
        expected = expected_by_kind.get(row_kind)
        if not expected:
            return None

        # net 行点名中可能包含形如 n2055 的数字；需要跳过 "(net)" 之前的数字，避免把网名尾号误判为 Fanout
        if row_kind == "net":
            attrs: Dict[str, str] = {name: "" for name in self.attrs_order}
            after_net = ""
            m = re.search(r"\(net\)", line, re.IGNORECASE)
            if m:
                after_net = line[m.end() :]
            nums = re.findall(r"-?\d+(?:\.\d+)?", after_net)
            if not nums:
                return None
            limit = min(len(nums), len(expected))
            for i, name in enumerate(expected[:limit]):
                attrs[name] = nums[i]
            return attrs

        # 在整行中提取数值 token，并从行尾向前取对应数量，适配不同列宽与轻微错位
        tokens_iter = list(re.finditer(r"-?\d+(?:\.\d+)?", line))
        if not tokens_iter:
            return None
        tokens = [m.group(0) for m in tokens_iter]

        attrs: Dict[str, str] = {name: "" for name in self.attrs_order}
        limit = min(len(tokens), len(expected))
        tail = tokens[-limit:] if limit else []
        for i, name in enumerate(expected[:limit]):
            attrs[name] = tail[i]
        return attrs

    def buildPointRow(
        self,
        meta: dict[str, Any],
        point_index: int,
        point: str,
        attrs: dict[str, Any],
    ) -> dict[str, Any]:
        """同基类；PT 抽取结果去掉 Incr 的 &，Fanout 整数，Cap/Trans/Derate/Mean/Sensit/Incr/Path 保留 4 位小数。"""
        row = super().buildPointRow(meta, point_index, point, attrs)
        incr = row.get("Incr", "")
        if isinstance(incr, str) and "&" in incr:
            row["Incr"] = incr.replace("&", "").strip()
        for col in [PT_FANOUT_COL] + list(PT_FLOAT_COLS):
            if col in row and row[col] not in (None, ""):
                row[col] = _format_pt_metric_for_csv(col, row[col])
        return row

