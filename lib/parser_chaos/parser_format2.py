"""
parser_chaos Format2 单条 Path 解析器。

从 Format2 path 文本中解析 Path Start/Path End/slack 等 meta，
以及 launch/capture 表格行（Type/Fanout/Cap/Delay/Time/Description 等）。
与 lib.parsers 完全独立。
"""
from __future__ import annotations

import re
from typing import Any

from .utils import extractColumnPositions, fillUncertainty

# Format2 表头列顺序（用于定位列与写出 CSV）
ATTRS_ORDER = [
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

_RE_PATH_START = re.compile(
    r"^\s*Path Start\s+:\s+(.+?)\s+\(\s*flip-flop[^)]*,\s*(\w+)\s*\)\s*$"
)
_RE_PATH_END = re.compile(
    r"^\s*Path End\s+:\s+(.+?)\s+\(\s*flip-flop[^)]*,\s*(\w+)\s*\)\s*$"
)
_RE_SLACK_LINE = re.compile(r"slack\s*\((?:violated|met)\)", re.IGNORECASE)
_RE_SLACK_VALUE = re.compile(r"(-?\d+(?:\.\d+)?)\s+slack\s*\(", re.IGNORECASE)
_RE_SLACK_STATUS = re.compile(r"slack\s*\((\w+)\)", re.IGNORECASE)
_RE_SEP = re.compile(r"^-=+\s*$")
_RE_DATA_ARRIVAL = re.compile(r"data\s+arrival\s+time", re.IGNORECASE)
_RE_CLOCK_LINE = re.compile(r"^\s*clock\s+", re.IGNORECASE)


def parseOnePath(
    path_id: int, path_text: str
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """
    解析单条 Format2 path 文本，返回 (meta, launch_rows, capture_rows)。

    从 Path Start/Path End/slack 行提取 meta；定位 Type/Fanout/.../Description 表头，
    解析表格数据行，按 data arrival time 与 clock 行划分 launch 与 capture。
    """
    lines = path_text.splitlines()
    meta = _defaultMeta(path_id)
    _fillMetaFromHeader(lines, meta)
    col_pos, table_start = _findTableStart(lines)
    if not col_pos or "Description" not in col_pos:
        return meta, [], []
    launch_rows: list[dict[str, Any]] = []
    capture_rows: list[dict[str, Any]] = []
    _parseTableSegment(
        lines, meta, col_pos, table_start, launch_rows, capture_rows
    )
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
    """从 Path Start / Path End / slack 行填充 meta。"""
    for line in lines:
        m = _RE_PATH_START.match(line.strip())
        if m:
            meta["startpoint"] = m.group(1).strip()
            meta["startpoint_clock"] = m.group(2).strip()
            continue
        m = _RE_PATH_END.match(line.strip())
        if m:
            meta["endpoint"] = m.group(1).strip()
            meta["endpoint_clock"] = m.group(2).strip()
            continue
        if _RE_SLACK_LINE.search(line):
            vm = _RE_SLACK_VALUE.search(line)
            if vm:
                meta["slack"] = vm.group(1).strip()
            else:
                nums = re.findall(r"-?\d+(?:\.\d+)?", line)
                if nums:
                    meta["slack"] = nums[-1]
            sm = _RE_SLACK_STATUS.search(line)
            if sm:
                meta["slack_status"] = sm.group(1).strip().upper()
            break


def _findTableStart(lines: list[str]) -> tuple[dict[str, int], int]:
    """定位表头行（Type, Fanout, Cap, ..., Description）与数据起始行。"""
    col_pos: dict[str, int] = {}
    table_start = 0
    for idx, line in enumerate(lines):
        if "Type" in line and "Fanout" in line and "Cap" in line and "Description" in line:
            col_pos = extractColumnPositions(line, ATTRS_ORDER)
            if col_pos:
                table_start = idx + 1
                if table_start < len(lines) and _RE_SEP.match(lines[table_start].strip()):
                    table_start += 1
                break
    return col_pos, table_start


def _valuesByColumns(content: str, col_pos: dict[str, int]) -> dict[str, str]:
    """按列位置从一行截取各列值。"""
    ordered = sorted(
        [n for n in ATTRS_ORDER if n in col_pos],
        key=lambda x: col_pos[x],
    )
    if not ordered:
        return {}
    out: dict[str, str] = {}
    for i, name in enumerate(ordered):
        start = col_pos[name]
        end = col_pos[ordered[i + 1]] if i + 1 < len(ordered) else len(content)
        value = content[start:end].strip() if start < len(content) else ""
        if value in ("-", "-0.000"):
            value = ""
        out[name] = value
    return out


def _descToPoint(desc: str) -> str:
    """从 Description 列内容得到 point 名（去掉前导 / 或 \\ 及空格）。"""
    if not desc:
        return ""
    s = desc.strip()
    if s.startswith("/ "):
        s = s[2:].strip()
    elif s.startswith("\\ "):
        s = s[2:].strip()
    return s.strip()


def _triggerEdgeFromLine(line: str) -> str:
    """从行中 / 或 \\ 得到 trigger_edge。"""
    if " / " in line:
        return "r"
    if " \\ " in line:
        return "f"
    return ""


def _parseTableSegment(
    lines: list[str],
    meta: dict[str, Any],
    col_pos: dict[str, int],
    table_start: int,
    launch_rows: list[dict[str, Any]],
    capture_rows: list[dict[str, Any]],
) -> None:
    """遍历表格数据行，按 data arrival time 与 clock 划分 launch / capture。"""
    in_launch = True
    in_capture = False
    launch_start_idx = -1
    capture_start_idx = -1
    for j in range(table_start, len(lines)):
        line = lines[j]
        stripped = line.strip()
        if _RE_SEP.match(stripped):
            # 分隔符后为 summary 行（required/arrival/slack），不归入 capture
            if in_capture:
                break
            continue
        if not stripped:
            continue
        raw = _valuesByColumns(line, col_pos)
        if not raw:
            continue
        type_str = (raw.get("Type") or "").strip().lower()
        desc = (raw.get("Description") or "").strip()
        point = _descToPoint(desc) if desc else ""
        if not point and type_str not in ("required", "arrival", "slack"):
            if "data arrival time" in line or "data required time" in line:
                point = "data arrival time" if "data arrival time" in line else "data required time"
            else:
                continue
        if "data arrival time" in line:
            m = re.search(
                r"(-?\d+\.\d+)\s+data\s+arrival\s+time",
                line,
                re.IGNORECASE,
            )
            if m:
                meta["arrival_time"] = m.group(1).strip()
            row = _buildPointRow(
                meta, len(launch_rows) + len(capture_rows) + 1, point, raw, line
            )
            if in_launch:
                launch_rows.append(row)
                in_launch = False
                in_capture = True
            continue
        if in_launch:
            if _RE_CLOCK_LINE.match(stripped) and launch_start_idx < 0:
                launch_start_idx = j
            row = _buildPointRow(
                meta, len(launch_rows) + 1, point, raw, line
            )
            launch_rows.append(row)
            continue
        if in_capture:
            if _RE_CLOCK_LINE.match(stripped) and capture_start_idx < 0:
                capture_start_idx = j
            if _RE_SLACK_LINE.search(line):
                row = _buildPointRow(
                    meta, len(launch_rows) + len(capture_rows) + 1, point, raw, line
                )
                capture_rows.append(row)
                break
            row = _buildPointRow(
                meta, len(launch_rows) + len(capture_rows) + 1, point, raw, line
            )
            capture_rows.append(row)


def _buildPointRow(
    meta: dict[str, Any],
    point_index: int,
    point: str,
    raw: dict[str, str],
    full_line: str = "",
) -> dict[str, Any]:
    """构建一行点表数据（含 meta 与各列属性）。"""
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
        row[name] = raw.get(name, "")
    row["trigger_edge"] = _triggerEdgeFromLine(full_line)
    return row


def _fillRequiredAndArrival(lines: list[str], meta: dict[str, Any]) -> None:
    """从行文本中补全 data required time（若前面未填）。"""
    if meta.get("required_time"):
        return
    for line in lines:
        if "data required time" in line:
            m = re.search(
                r"(-?\d+\.\d+)\s+data\s+required\s+time",
                line,
                re.IGNORECASE,
            )
            if m:
                meta["required_time"] = m.group(1).strip()
            break
