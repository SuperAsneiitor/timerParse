"""
PT（PrimeTime 风格）Timing 报告解析器。

继承 Format1Parser，覆盖表头与正则以匹配 PT 的 Startpoint/Endpoint（无括号类型）、
Mean/Sensit 列及 library setup/hold 行。
"""
from __future__ import annotations

import re
from typing import Any

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
    _re_point_header = re.compile(r"^\s+Point\s+", re.IGNORECASE)
    _re_sep_line = re.compile(r"^\s+-{3,}\s*$")
    _re_clock_rise = re.compile(r"^\s+clock\s+\S+\s+\(rise\s+edge\)\s")
    _re_data_arrival = re.compile(r"^\s+data\s+arrival\s+time\s")
    _re_library_setup = re.compile(r"^\s+library\s+(setup|hold)\s+time\s")

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
                    point, attrs = self.parseFixedWidthAttrs(lines[k], col_pos, self.attrs_order)
                    if not point:
                        continue
                    ptype = self._inferPointType(point)
                    if ptype in ("input_pin", "output_pin"):
                        attrs = self._extractTriggerEdgeFromPath(attrs)
                    filtered = self.applyTypeFilter(attrs, ptype, k - launch_start_idx)
                    launch_rows.append(self.buildPointRow(meta, len(launch_rows) + 1, point, filtered))
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
            if in_capture and self._re_library_setup.match(lines[j]):
                for k in range(capture_start_idx, j):
                    point, attrs = self.parseFixedWidthAttrs(lines[k], col_pos, self.attrs_order)
                    if not point:
                        continue
                    ptype = self._inferPointType(point)
                    if ptype in ("input_pin", "output_pin"):
                        attrs = self._extractTriggerEdgeFromPath(attrs)
                    filtered = self.applyTypeFilter(attrs, ptype, k - capture_start_idx)
                    capture_rows.append(self.buildPointRow(meta, len(capture_rows) + 1, point, filtered))
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
        return meta, launch_rows, capture_rows

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

