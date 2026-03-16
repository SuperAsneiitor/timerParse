"""
parser_chaos Format1（APR）单条 Path 解析器。

根据 Format1 报告的单条 path 文本解析出 meta、launch_rows、capture_rows。
与 lib.parsers 完全独立，逻辑自包含（表头、Point 表、clock/data arrival/library setup 边界）。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from .utils import extractColumnPositions, fillUncertainty, parseFixedWidthAttrs

# Format1 点表列顺序与类型过滤配置
ATTRS_ORDER = ["Fanout", "Cap", "Trans", "Location", "Incr", "Path", "trigger_edge"]
SKIP_FIRST_ROWS = 2
ATTRS_BY_TYPE = {
    "net": ["Fanout"],
    "input_pin": ["Cap", "Trans", "Location", "Incr", "Path", "trigger_edge"],
    "output_pin": ["Cap", "Trans", "Location", "Incr", "Path", "trigger_edge"],
}
OUTPUT_PIN_NAMES = frozenset({"Q", "Z", "ZN", "ZP"})

_RE_STARTPOINT = re.compile(r"^\s*Startpoint:\s+(.+?)\s+\(.+\)\s*$")
_RE_ENDPOINT = re.compile(r"^\s*Endpoint:\s+(.+?)\s+\(.+\)\s*$")
_RE_CLOCKED_BY = re.compile(r"clocked by ([^\s)]+)")
_RE_SLACK = re.compile(r"^\s*slack\s+\((VIOLATED|MET)\)(?:\s|$)")
_RE_SLACK_VALUE = re.compile(r"(-?\d+\.\d+)\s*$")
_RE_POINT_HEADER = re.compile(r"^\s*Point\s+", re.IGNORECASE)
_RE_SEP_LINE = re.compile(r"^\s*-{3,}\s*$")
_RE_CLOCK_START = re.compile(
    r"^\s*clock\s+\S+(?:\s+\((?:rise|fall)\s+edge\))?\s+(?=[-\d])",
    re.IGNORECASE,
)
_RE_DATA_ARRIVAL = re.compile(r"^\s*data\s+arrival\s+time(?:\s|$)")
_RE_LIBRARY_SETUP = re.compile(r"^\s*library\s+setup\s+time(?:\s|$)")


def parseOnePath(path_id: int, path_text: str) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """
    解析单条 Format1 path 文本，返回 (meta, launch_rows, capture_rows)。

    逻辑：先解析表头得到 meta（startpoint/endpoint/slack 等），再定位 Point 表头与列位置，
    按 clock / data arrival / library setup 边界解析 launch 与 capture 表格行。
    """
    lines = path_text.splitlines()
    meta = _defaultMeta(path_id)
    launch_rows: list[dict[str, Any]] = []
    capture_rows: list[dict[str, Any]] = []
    _fillMetaFromHeader(lines, meta)
    col_pos, table_start = _findTableStart(lines)
    _parseLaunchSegment(lines, meta, col_pos, table_start, launch_rows)
    _parseCaptureSegment(lines, meta, col_pos, table_start, capture_rows)
    _fillRequiredAndArrival(lines, meta)
    fillUncertainty(lines, meta)
    return meta, launch_rows, capture_rows


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


def _fillMetaFromHeader(lines: list[str], meta: dict[str, Any]) -> None:
    """从 path 文本前部解析 Startpoint/Endpoint/slack 等写入 meta。"""
    for line in lines:
        m = _RE_STARTPOINT.match(line)
        if m:
            meta["startpoint"] = m.group(1).strip()
            cm = _RE_CLOCKED_BY.search(line)
            meta["startpoint_clock"] = cm.group(1).strip() if cm else ""
            continue
        m = _RE_ENDPOINT.match(line)
        if m:
            meta["endpoint"] = m.group(1).strip()
            cm = _RE_CLOCKED_BY.search(line)
            meta["endpoint_clock"] = cm.group(1).strip() if cm else ""
            continue
        m = _RE_SLACK.match(line)
        if m:
            meta["slack_status"] = m.group(1).strip()
            vm = _RE_SLACK_VALUE.search(line)
            meta["slack"] = vm.group(1).strip() if vm else ""
            break


def _findTableStart(lines: list[str]) -> tuple[dict[str, int], int]:
    """定位 Point 表头行与列位置，返回 (col_pos, table_start_row)。"""
    col_pos: dict[str, int] = {}
    table_start = 0
    for idx, line in enumerate(lines):
        if _RE_POINT_HEADER.match(line):
            col_pos = extractColumnPositions(line, ATTRS_ORDER)
            if "Location" in col_pos:
                table_start = idx + 1
                if table_start < len(lines) and _RE_SEP_LINE.match(lines[table_start]):
                    table_start += 1
                break
            col_pos = {}
    return col_pos, table_start


def _classify_row_kind(
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
    if _RE_CLOCK_START.match(line):
        return "clock"
    if "(net)" in (point or ""):
        return "net"
    if in_launch and segment_row_index >= 0:
        return "pin"
    return ""


def _parse_numeric_columns(
    line: str,
    col_pos: dict[str, int],
    row_kind: str,
) -> Dict[str, str] | None:
    """
    基于 row_kind + 数值 token 顺序解析当前行的数值列。

    若无法可靠映射（无数字或 row_kind 未知），返回 None，调用方应回退到 parseFixedWidthAttrs 的 attrs。
    """
    if not row_kind:
        return None
    tokens = re.findall(r"-?\d+(?:\.\d+)?", line)
    if not tokens:
        return None

    # 仅针对易截断的 Incr/Path 使用数值顺序解析，Fanout/Cap/Trans 保持定宽结果，
    # 与 lib.parsers 中 Format1Parser 的策略保持一致。
    attrs: Dict[str, str] = {name: "" for name in ATTRS_ORDER}
    if row_kind == "clock":
        if len(tokens) >= 2:
            attrs["Incr"] = tokens[-2]
            attrs["Path"] = tokens[-1]
        elif len(tokens) == 1:
            attrs["Path"] = tokens[-1]
        return attrs

    if row_kind == "net":
        if len(tokens) >= 2:
            attrs["Incr"] = tokens[-2]
            attrs["Path"] = tokens[-1]
        elif len(tokens) == 1:
            attrs["Path"] = tokens[-1]
        return attrs

    if row_kind == "pin":
        if len(tokens) >= 2:
            attrs["Incr"] = tokens[-2]
            attrs["Path"] = tokens[-1]
        elif len(tokens) == 1:
            attrs["Path"] = tokens[-1]
        return attrs

    return attrs


def _parseLaunchSegment(
    lines: list[str],
    meta: dict[str, Any],
    col_pos: dict[str, int],
    table_start: int,
    launch_rows: list[dict[str, Any]],
) -> None:
    """从表格区解析 launch 段：从 clock 行到 data arrival time 行。"""
    in_launch = False
    launch_start_idx = -1
    for j in range(table_start, len(lines)):
        if _RE_CLOCK_START.match(lines[j]):
            in_launch = True
            launch_start_idx = j
            continue
        if in_launch and _RE_DATA_ARRIVAL.match(lines[j]):
            for k in range(launch_start_idx, j + 1):
                raw_point, base_attrs = parseFixedWidthAttrs(
                    lines[k], col_pos, ATTRS_ORDER
                )
                if not raw_point:
                    continue
                row_kind = _classify_row_kind(
                    raw_point, lines[k], k - launch_start_idx, in_launch=True
                )
                smart_numeric = _parse_numeric_columns(lines[k], col_pos, row_kind)
                attrs = base_attrs.copy()
                if smart_numeric:
                    for col, val in smart_numeric.items():
                        if val:
                            attrs[col] = val
                ptype = _inferPointType(raw_point)
                if ptype in ("input_pin", "output_pin"):
                    attrs = _extractTriggerEdgeFromPath(attrs)
                    if not attrs.get("trigger_edge"):
                        attrs["trigger_edge"] = _extractTriggerEdgeFromLine(lines[k])
                filtered = _applyTypeFilter(attrs, ptype, k - launch_start_idx)
                launch_rows.append(
                    _buildPointRow(meta, len(launch_rows) + 1, raw_point, filtered)
                )
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
    """从表格区解析 capture 段：data arrival 之后的 clock 行到 library setup 行。"""
    after_data_arrival = False
    in_capture = False
    capture_start_idx = -1
    for j in range(table_start, len(lines)):
        if _RE_DATA_ARRIVAL.match(lines[j]):
            after_data_arrival = True
            continue
        if after_data_arrival and _RE_CLOCK_START.match(lines[j]):
            in_capture = True
            capture_start_idx = j
            continue
        if in_capture and _RE_LIBRARY_SETUP.match(lines[j]):
            for k in range(capture_start_idx, j):
                raw_point, base_attrs = parseFixedWidthAttrs(
                    lines[k], col_pos, ATTRS_ORDER
                )
                if not raw_point:
                    continue
                row_kind = _classify_row_kind(
                    raw_point, lines[k], k - capture_start_idx, in_launch=False
                )
                smart_numeric = _parse_numeric_columns(lines[k], col_pos, row_kind)
                attrs = base_attrs.copy()
                if smart_numeric:
                    for col, val in smart_numeric.items():
                        if val:
                            attrs[col] = val
                ptype = _inferPointType(raw_point)
                if ptype in ("input_pin", "output_pin"):
                    attrs = _extractTriggerEdgeFromPath(attrs)
                    if not attrs.get("trigger_edge"):
                        attrs["trigger_edge"] = _extractTriggerEdgeFromLine(lines[k])
                filtered = _applyTypeFilter(attrs, ptype, k - capture_start_idx)
                capture_rows.append(
                    _buildPointRow(meta, len(capture_rows) + 1, raw_point, filtered)
                )
            break


def _fillRequiredAndArrival(lines: list[str], meta: dict[str, Any]) -> None:
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


def _extractTriggerEdgeFromPath(attrs: dict[str, Any]) -> dict[str, Any]:
    """从 Path 列末尾提取 r/f 作为 trigger_edge，并从 Path 中移除该后缀。"""
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


def _extractTriggerEdgeFromLine(line: str) -> str:
    """从整行末尾提取 trigger_edge（r/f）。"""
    m = re.search(r"\s([rf])\s*$", line.strip(), re.IGNORECASE)
    return m.group(1).lower() if m else ""


def _inferPointType(point_name: str) -> str:
    """根据 point 名称推断类型：net / output_pin / input_pin。"""
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
    """按 point_type 与 segment_row_index 过滤属性：前 skip 行及非允许列置空。"""
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
    """根据 meta 与当前点属性构建一行点表数据。"""
    row: dict[str, Any] = {
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
    return row
