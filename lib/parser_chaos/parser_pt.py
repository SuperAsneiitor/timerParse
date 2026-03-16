"""
parser_chaos PT（PrimeTime）单条 Path 解析器。

与 Format1 类似，但表头为正则匹配 Startpoint/Endpoint（无括号）、
点表含 Derate/Mean/Sensit，library 行为 setup|hold。与 lib.parsers 完全独立。
"""
from __future__ import annotations

import re
from typing import Any

from .utils import extractColumnPositions, fillUncertainty, parseFixedWidthAttrs

ATTRS_ORDER = ["Fanout", "Cap", "Trans", "Derate", "Mean", "Sensit", "Incr", "Path", "trigger_edge"]
SKIP_FIRST_ROWS = 2
ATTRS_BY_TYPE = {
    "net": ["Fanout", "Cap"],
    "input_pin": ["Trans", "Derate", "Mean", "Sensit", "Incr", "Path", "trigger_edge"],
    "output_pin": ["Trans", "Derate", "Mean", "Sensit", "Incr", "Path", "trigger_edge"],
}
OUTPUT_PIN_NAMES = frozenset({"Q", "Z", "ZN", "ZP"})

_RE_STARTPOINT = re.compile(r"^\s+Startpoint:\s+(.+?)\s*$")
_RE_ENDPOINT = re.compile(r"^\s+Endpoint:\s+(.+?)\s*$")
_RE_CLOCKED_BY = re.compile(r"clocked by ([^\s)]+)")
_RE_SLACK = re.compile(r"^\s+slack\s+\((VIOLATED|MET)\)\s")
_RE_SLACK_VALUE = re.compile(r"(-?\d+\.\d+)\s*$")
_RE_POINT_HEADER = re.compile(r"^\s+Point\s+", re.IGNORECASE)
_RE_SEP_LINE = re.compile(r"^\s+-{3,}\s*$")
_RE_CLOCK_RISE = re.compile(r"^\s+clock\s+\S+\s+\(rise\s+edge\)\s")
_RE_DATA_ARRIVAL = re.compile(r"^\s+data\s+arrival\s+time\s")
_RE_LIBRARY_SETUP = re.compile(r"^\s+library\s+(setup|hold)\s+time\s")


def parseOnePath(path_id: int, path_text: str) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """
    解析单条 PT path 文本，返回 (meta, launch_rows, capture_rows)。

    逻辑：表头用 PT 正则（Startpoint/Endpoint 无括号，clocked by 可能在下一行）；
    点表以 "Path" 列存在定位表头，按 clock rise / data arrival / library setup|hold 边界解析 launch/capture。
    """
    lines = path_text.splitlines()
    meta = _defaultMeta(path_id)
    launch_rows = []
    capture_rows = []
    _fillMetaFromHeader(lines, meta)
    col_pos, table_start = _findTableStart(lines)
    _parseLaunchSegment(lines, meta, col_pos, table_start, launch_rows)
    _parseCaptureSegment(lines, meta, col_pos, table_start, capture_rows)
    _fillRequiredAndArrival(lines, meta)
    fillUncertainty(lines, meta)
    return meta, launch_rows, capture_rows


def _defaultMeta(path_id: int) -> dict[str, Any]:
    """返回单 path 的默认 meta。"""
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


def _fillMetaFromHeader(lines: list[str], meta: dict[str, Any]) -> None:
    """PT 表头：Startpoint/Endpoint 可能无括号，clocked by 可能在下一行。"""
    for i, line in enumerate(lines):
        m = _RE_STARTPOINT.match(line)
        if m:
            meta["startpoint"] = m.group(1).strip()
            cm = _RE_CLOCKED_BY.search(line)
            if not cm and i + 1 < len(lines):
                cm = _RE_CLOCKED_BY.search(lines[i + 1])
            meta["startpoint_clock"] = cm.group(1).strip() if cm else ""
            continue
        m = _RE_ENDPOINT.match(line)
        if m:
            meta["endpoint"] = m.group(1).strip()
            cm = _RE_CLOCKED_BY.search(line)
            if not cm and i + 1 < len(lines):
                cm = _RE_CLOCKED_BY.search(lines[i + 1])
            meta["endpoint_clock"] = cm.group(1).strip() if cm else ""
            continue
        m = _RE_SLACK.match(line)
        if m:
            meta["slack_status"] = m.group(1).strip()
            vm = _RE_SLACK_VALUE.search(line)
            meta["slack"] = vm.group(1).strip() if vm else ""
            break


def _findTableStart(lines: list[str]) -> tuple[dict[str, int], int]:
    """PT 点表以 Point 表头且含 Path 列定位。"""
    col_pos = {}
    table_start = 0
    for idx, line in enumerate(lines):
        if _RE_POINT_HEADER.match(line):
            col_pos = extractColumnPositions(line, ATTRS_ORDER)
            if "Path" in col_pos:
                table_start = idx + 1
                if table_start < len(lines) and _RE_SEP_LINE.match(lines[table_start]):
                    table_start += 1
                break
            col_pos = {}
    return col_pos, table_start


def _parseLaunchSegment(
    lines: list[str],
    meta: dict[str, Any],
    col_pos: dict[str, int],
    table_start: int,
    launch_rows: list[dict[str, Any]],
) -> None:
    """Launch 段：clock (rise edge) 行到 data arrival time 行。"""
    in_launch = False
    launch_start_idx = -1
    for j in range(table_start, len(lines)):
        if _RE_CLOCK_RISE.match(lines[j]):
            in_launch = True
            launch_start_idx = j
            continue
        if in_launch and _RE_DATA_ARRIVAL.match(lines[j]):
            for k in range(launch_start_idx, j + 1):
                point, attrs = parseFixedWidthAttrs(lines[k], col_pos, ATTRS_ORDER)
                if not point:
                    continue
                ptype = _inferPointType(point)
                if ptype in ("input_pin", "output_pin"):
                    attrs = _extractTriggerEdgeFromPath(attrs)
                filtered = _applyTypeFilter(attrs, ptype, k - launch_start_idx)
                launch_rows.append(_buildPointRow(meta, len(launch_rows) + 1, point, filtered))
            vm = re.search(r"(-?\d+\.\d+)\s*$", lines[j])
            if vm:
                meta["arrival_time"] = vm.group(1).strip()
            break


def _parseCaptureSegment(
    lines: list[str],
    meta: dict[str, Any],
    col_pos: dict[str, int],
    table_start: int,
    capture_rows: list[dict[str, Any]],
) -> None:
    """Capture 段：data arrival 之后 clock 行到 library setup|hold 行。"""
    after_data_arrival = False
    in_capture = False
    capture_start_idx = -1
    for j in range(table_start, len(lines)):
        if _RE_DATA_ARRIVAL.match(lines[j]):
            after_data_arrival = True
            continue
        if after_data_arrival and _RE_CLOCK_RISE.match(lines[j]):
            in_capture = True
            capture_start_idx = j
            continue
        if in_capture and _RE_LIBRARY_SETUP.match(lines[j]):
            for k in range(capture_start_idx, j):
                point, attrs = parseFixedWidthAttrs(lines[k], col_pos, ATTRS_ORDER)
                if not point:
                    continue
                ptype = _inferPointType(point)
                if ptype in ("input_pin", "output_pin"):
                    attrs = _extractTriggerEdgeFromPath(attrs)
                filtered = _applyTypeFilter(attrs, ptype, k - capture_start_idx)
                capture_rows.append(_buildPointRow(meta, len(capture_rows) + 1, point, filtered))
            break


def _fillRequiredAndArrival(lines: list[str], meta: dict[str, Any]) -> None:
    """从行中补全 data required time / data arrival time。"""
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


def _extractTriggerEdgeFromPath(attrs: dict[str, Any]) -> dict[str, Any]:
    """从 Path 列末尾提取 r/f 作为 trigger_edge。"""
    path_val = str(attrs.get("Path", "") or "").strip()
    if not path_val:
        attrs["trigger_edge"] = ""
        return attrs
    tokens = path_val.split()
    if tokens and tokens[-1] in ("r", "f"):
        attrs["trigger_edge"] = tokens[-1]
        attrs["Path"] = " ".join(tokens[:-1])
    else:
        attrs.setdefault("trigger_edge", "")
    return attrs


def _inferPointType(point_name: str) -> str:
    """根据 point 名推断 net / output_pin / input_pin。"""
    if not point_name or "(net)" in point_name:
        return "net"
    m = re.search(r"/([A-Za-z0-9_\[\]]+)\s*\(?[A-Z]?", point_name)
    pin = m.group(1) if m else ""
    if pin in OUTPUT_PIN_NAMES:
        return "output_pin"
    return "input_pin"


def _applyTypeFilter(
    attrs: dict[str, Any],
    point_type: str,
    segment_row_index: int,
) -> dict[str, Any]:
    """按类型与行下标过滤属性。"""
    out = {name: attrs.get(name, "") for name in ATTRS_ORDER}
    if segment_row_index < SKIP_FIRST_ROWS:
        return out
    allowed = ATTRS_BY_TYPE.get(point_type)
    if not allowed:
        return out
    allowed_set = set(allowed)
    for name in ATTRS_ORDER:
        if name not in allowed_set:
            out[name] = ""
    return out


def _buildPointRow(
    meta: dict[str, Any],
    point_index: int,
    point: str,
    attrs: dict[str, Any],
) -> dict[str, Any]:
    """构建一行点表数据；PT 抽取结果中 Incr 不保留 & 符号。"""
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
    for name in ATTRS_ORDER:
        row[name] = attrs.get(name, "")
    incr = row.get("Incr", "")
    if isinstance(incr, str) and "&" in incr:
        row["Incr"] = incr.replace("&", "").strip()
    return row
