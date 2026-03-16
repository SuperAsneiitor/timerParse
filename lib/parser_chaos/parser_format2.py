"""
parser_chaos Format2 单条 Path 解析器。

重构为“行类型 + 数值 token 顺序”语义解析，避免依赖列起始位置做定宽截断。
与 lib.parsers 完全独立。
"""
from __future__ import annotations

import re
from typing import Any

from .utils import extractColumnPositions, fillUncertainty

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
    "trigger_edge",
    "Description",
]

_OUTPUT_PIN_NAMES = frozenset({"Q", "Z", "ZN", "ZP"})

_RE_PATH_START = re.compile(
    r"^\s*Path Start\s+:\s+(.+?)\s+\(\s*flip-flop[^)]*,\s*(\w+)\s*\)\s*$"
)
_RE_PATH_END = re.compile(
    r"^\s*Path End\s+:\s+(.+?)\s+\(\s*flip-flop[^)]*,\s*(\w+)\s*\)\s*$"
)
_RE_SLACK_LINE = re.compile(r"slack\s*\((?:violated|met)\)", re.IGNORECASE)
_RE_SLACK_VALUE_BEFORE = re.compile(
    r"(-?\d+(?:\.\d+)?)\s+slack\s*\(",
    re.IGNORECASE,
)
_RE_SLACK_VALUE_AFTER = re.compile(
    r"slack\s*\(\w+\)\s*[:=]?\s*(-?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_RE_SLACK_STATUS = re.compile(r"slack\s*\((\w+)\)", re.IGNORECASE)
_RE_SEP = re.compile(r"^-=+\s*$")
_RE_DATA_ARRIVAL = re.compile(r"data arrival time", re.IGNORECASE)


def parseOnePath(
    path_id: int,
    path_text: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """解析单条 Format2 path 文本。"""
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
        m = _RE_PATH_START.match(line)
        if m:
            meta["startpoint"] = m.group(1).strip()
            meta["startpoint_clock"] = m.group(2).strip()
            continue
        m = _RE_PATH_END.match(line)
        if m:
            meta["endpoint"] = m.group(1).strip()
            meta["endpoint_clock"] = m.group(2).strip()
            continue
        if _RE_SLACK_LINE.search(line):
            vm = _RE_SLACK_VALUE_BEFORE.search(line) or _RE_SLACK_VALUE_AFTER.search(line)
            sm = _RE_SLACK_STATUS.search(line)
            if vm:
                meta["slack"] = vm.group(1).strip()
            else:
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
            col_pos = extractColumnPositions(line, ATTRS_ORDER)
            if "Description" in col_pos:
                table_start = idx + 1
                if table_start < len(lines) and _RE_SEP.match(lines[table_start]):
                    table_start += 1
                break
            col_pos = {}

    in_launch = True
    in_capture = False
    for j in range(table_start, len(lines)):
        line = lines[j]
        stripped = line.strip()
        if not stripped:
            continue
        if _RE_SEP.match(stripped):
            if in_capture:
                break
            continue
        # 跳过表头分隔线/调试分隔线
        if set(stripped) <= {"-", "="}:
            continue
        if stripped.lower().startswith("type "):
            continue

        point, attrs, point_type = _parseLineByType(line, col_pos)
        if not point and point_type not in ("required", "arrival", "slack"):
            continue

        if _RE_DATA_ARRIVAL.search(line):
            if in_launch:
                vm = re.search(
                    r"(-?\d+\.\d+)\s+data\s+arrival\s+time",
                    line,
                    re.IGNORECASE,
                )
                if vm:
                    meta["arrival_time"] = vm.group(1).strip()
            launch_rows.append(_buildPointRow(meta, len(launch_rows) + 1, point, attrs))
            in_launch = False
            in_capture = True
            continue

        if in_launch:
            launch_rows.append(_buildPointRow(meta, len(launch_rows) + 1, point, attrs))
        elif in_capture:
            capture_rows.append(_buildPointRow(meta, len(capture_rows) + 1, point, attrs))

    _fillRequiredAndArrival(lines, meta)
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

    fillUncertainty(lines, meta)
    return meta, launch_rows, capture_rows


def _buildPointRow(
    meta: dict[str, Any],
    point_index: int,
    point: str,
    attrs: dict[str, str],
) -> dict[str, Any]:
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


def _fillRequiredAndArrival(lines: list[str], meta: dict[str, Any]) -> None:
    for line in lines:
        if "data required time" in line:
            vm = re.search(
                r"(-?\d+\.\d+)\s+data\s+required\s+time",
                line,
                re.IGNORECASE,
            )
            if vm:
                meta["required_time"] = vm.group(1).strip()
            break


def _parseLineByType(
    line: str,
    col_pos: dict[str, int],
) -> tuple[str, dict[str, str], str]:
    """按行类型路由到语义解析函数。"""
    content = line.rstrip()
    if not content.strip():
        return "", {}, "other"

    raw = _valuesByColumns(content, col_pos) if col_pos else {}
    type_str = (raw.get("Type") or "").strip().lower()
    if not type_str:
        first = content.strip().split()
        type_str = first[0].lower() if first else ""
    if type_str == "pin":
        desc_col = _descFromContent(content, col_pos)
        pin_name = _pinNameFromDesc(desc_col)
        type_str = "output_pin" if pin_name in _OUTPUT_PIN_NAMES else "input_pin"

    parsers = {
        "input_pin": _parseInputPin,
        "output_pin": _parseOutputPin,
        "net": _parseNet,
        "clock": _parseClock,
        "port": _parsePort,
        "constraint": _parseConstraint,
        "required": _parseRequired,
        "arrival": _parseArrival,
        "slack": _parseSlack,
    }
    parser = parsers.get(type_str)
    if not parser:
        return "", {}, "other"
    point_name, attrs = parser(raw, content, col_pos)
    return point_name, attrs, type_str


def _valuesByColumns(content: str, col_pos: dict[str, int]) -> dict[str, str]:
    ordered = sorted([n for n in ATTRS_ORDER if n in col_pos], key=lambda x: col_pos[x])
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


def _descFromContent(content: str, col_pos: dict[str, int]) -> str:
    if "Description" not in col_pos:
        return ""
    return content[col_pos["Description"] :].strip()


def _descFromPinLine(content: str) -> str:
    line = content.strip()
    m = re.search(r"\s[/\\]\s*(.+)$", line)
    if m:
        return m.group(1).strip()
    return ""


def _triggerEdgeFromLine(content: str) -> str:
    line = content.strip()
    m = re.search(r"\s([/\\])\s*(?:\S.*)?$", line)
    if m:
        return "r" if m.group(1) == "/" else "f"
    return ""


def _firstNumericFromCell(value: str) -> str:
    m = re.search(r"-?\d+(?:\.\d+)?", str(value or ""))
    return m.group(0) if m else ""


def _splitDerateAndXy(derate_cell: str) -> tuple[str, str, str]:
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


def _xyCellFromRaw(raw: dict[str, str]) -> str:
    return ((raw.get("x-coord") or "").strip() + " " + (raw.get("y-coord") or "").strip()).strip()


def _parseXy(value: str, which: str) -> str:
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


def _isReasonableNum(s: str, max_abs: float = 10.0) -> bool:
    try:
        v = float(str(s).strip())
        return abs(v) <= max_abs
    except Exception:
        return False


def _extractPinMetrics(content: str, is_output: bool) -> tuple[str, str, str, str, str, str, str]:
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
            if len(nums) >= 3:
                trans, delay, time = nums[-3], nums[-2], nums[-1]
            elif len(nums) == 2:
                delay, time = nums[-2], nums[-1]
            elif len(nums) == 1:
                time = nums[-1]
        else:
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


def _parseInputPin(
    raw: dict[str, str],
    content: str,
    col_pos: dict[str, int],
) -> tuple[str, dict[str, str]]:
    attrs = {k: "" for k in ATTRS_ORDER}
    prefix_area = content[: col_pos["Description"]] if "Description" in col_pos else content
    trans, derate, x_val, y_val, d_delay, delay, time = _extractPinMetrics(prefix_area, is_output=False)
    attrs["Derate"] = derate or (raw.get("Derate") or "").strip().replace(" ", "")
    attrs["x-coord"] = x_val or _parseXy(_xyCellFromRaw(raw), "x-coord")
    attrs["y-coord"] = y_val or _parseXy(_xyCellFromRaw(raw), "y-coord")
    raw_dtrans = (raw.get("D-Trans") or "").strip()
    raw_trans = (raw.get("Trans") or "").strip()
    attrs["D-Trans"] = raw_dtrans if _isReasonableNum(raw_dtrans, 1.0) else ""
    attrs["Trans"] = trans if _isReasonableNum(trans, 1.0) else (raw_trans if _isReasonableNum(raw_trans, 1.0) else "")
    attrs["Type"] = "pin"
    raw_ddelay = (raw.get("D-Delay") or "").strip()
    raw_delay = (raw.get("Delay") or "").strip()
    raw_time = (raw.get("Time") or "").strip()
    attrs["D-Delay"] = d_delay if _isReasonableNum(d_delay, 2.0) else (raw_ddelay if _isReasonableNum(raw_ddelay, 2.0) else "")
    attrs["Delay"] = delay if _isReasonableNum(delay, 10.0) else (raw_delay if _isReasonableNum(raw_delay, 10.0) else "")
    attrs["Time"] = time if _isReasonableNum(time, 20.0) else (raw_time if _isReasonableNum(raw_time, 20.0) else "")
    attrs["trigger_edge"] = _triggerEdgeFromLine(content)
    desc = _descFromPinLine(content) or _descFromContent(content, col_pos)
    point = _descToPoint(desc)
    attrs["Description"] = point
    return point, attrs


def _parseOutputPin(
    raw: dict[str, str],
    content: str,
    col_pos: dict[str, int],
) -> tuple[str, dict[str, str]]:
    attrs = {k: "" for k in ATTRS_ORDER}
    prefix_area = content[: col_pos["Description"]] if "Description" in col_pos else content
    trans, derate, x_val, y_val, _d_delay, delay, time = _extractPinMetrics(prefix_area, is_output=True)
    attrs["Derate"] = derate or (raw.get("Derate") or "").strip().replace(" ", "")
    attrs["x-coord"] = x_val or _parseXy(_xyCellFromRaw(raw), "x-coord")
    attrs["y-coord"] = y_val or _parseXy(_xyCellFromRaw(raw), "y-coord")
    raw_trans = (raw.get("Trans") or "").strip()
    attrs["Trans"] = trans if _isReasonableNum(trans, 1.0) else (raw_trans if _isReasonableNum(raw_trans, 1.0) else "")
    attrs["Type"] = "pin"
    raw_delay = (raw.get("Delay") or "").strip()
    raw_time = (raw.get("Time") or "").strip()
    attrs["Delay"] = delay if _isReasonableNum(delay, 10.0) else (raw_delay if _isReasonableNum(raw_delay, 10.0) else "")
    attrs["Time"] = time if _isReasonableNum(time, 20.0) else (raw_time if _isReasonableNum(raw_time, 20.0) else "")
    attrs["trigger_edge"] = _triggerEdgeFromLine(content)
    desc = _descFromPinLine(content) or _descFromContent(content, col_pos)
    point = _descToPoint(desc)
    attrs["Description"] = point
    return point, attrs


def _parseNet(
    raw: dict[str, str],
    content: str,
    col_pos: dict[str, int],
) -> tuple[str, dict[str, str]]:
    attrs = {k: "" for k in ATTRS_ORDER}
    attrs["Type"] = "net"
    m = re.match(
        r"^\s*net\s+(\d+)\s+(-?\d+(?:\.\d+)?)\s*(?:xd\b)?\s*(.*)$",
        content,
        re.IGNORECASE,
    )
    if m:
        attrs["Fanout"] = m.group(1).strip()
        attrs["Cap"] = m.group(2).strip()
        point = _descToPoint(m.group(3).strip())
        attrs["Description"] = point
        return point, attrs
    # 回退：尽量从 token 提取
    tokens = content.split()
    if len(tokens) >= 3 and tokens[0].lower() == "net":
        attrs["Fanout"] = tokens[1]
        attrs["Cap"] = tokens[2]
        desc_start = 3 + (1 if len(tokens) > 3 and tokens[3].lower() == "xd" else 0)
        point = _descToPoint(" ".join(tokens[desc_start:]))
        attrs["Description"] = point
        return point, attrs
    return "", attrs


def _parseClock(
    raw: dict[str, str],
    content: str,
    col_pos: dict[str, int],
) -> tuple[str, dict[str, str]]:
    attrs = {k: "" for k in ATTRS_ORDER}
    attrs["Type"] = "clock"
    values, desc = _tailNNumericAndDesc(content, 2)
    if len(values) >= 2:
        attrs["Delay"], attrs["Time"] = values[0], values[1]
    elif len(values) == 1:
        attrs["Time"] = values[0]
    point = _descToPoint(desc)
    attrs["Description"] = point
    return point, attrs


def _parsePort(
    raw: dict[str, str],
    content: str,
    col_pos: dict[str, int],
) -> tuple[str, dict[str, str]]:
    attrs = {k: "" for k in ATTRS_ORDER}
    attrs["Type"] = "port"
    attrs["Trans"] = (raw.get("Trans") or "").strip()
    derate_raw = (raw.get("Derate") or "").strip()
    if "{" in derate_raw:
        _, x_val, y_val = _splitDerateAndXy(derate_raw)
        attrs["x-coord"] = x_val
        attrs["y-coord"] = y_val
    else:
        xy_cell = _xyCellFromRaw(raw)
        attrs["x-coord"] = _parseXy(xy_cell, "x-coord")
        attrs["y-coord"] = _parseXy(xy_cell, "y-coord")
    raw_delay = _firstNumericFromCell(raw.get("Delay", ""))
    raw_time = _firstNumericFromCell(raw.get("Time", ""))
    values, desc = _tailNNumericAndDesc(content, 2)
    if len(values) >= 2:
        attrs["Delay"], attrs["Time"] = values[0], values[1]
    elif len(values) == 1:
        attrs["Delay"], attrs["Time"] = raw_delay, values[0]
    else:
        attrs["Delay"], attrs["Time"] = raw_delay, raw_time
    attrs["trigger_edge"] = _triggerEdgeFromLine(content)
    desc = _descFromPinLine(content) or desc
    point = _descToPoint(desc)
    attrs["Description"] = point
    return point, attrs


def _parseConstraint(
    raw: dict[str, str],
    content: str,
    col_pos: dict[str, int],
) -> tuple[str, dict[str, str]]:
    attrs = {k: "" for k in ATTRS_ORDER}
    attrs["Type"] = "constraint"
    values, desc = _tailNNumericAndDesc(content, 2)
    if len(values) >= 2:
        attrs["Delay"], attrs["Time"] = values[0], values[1]
    elif len(values) == 1:
        attrs["Time"] = values[0]
    point = _descToPoint(desc)
    attrs["Description"] = point
    return point, attrs


def _parseRequired(
    raw: dict[str, str],
    content: str,
    col_pos: dict[str, int],
) -> tuple[str, dict[str, str]]:
    attrs = {k: "" for k in ATTRS_ORDER}
    attrs["Type"] = "required"
    values, desc = _tailNNumericAndDesc(content, 1)
    if values:
        attrs["Time"] = values[0]
    point = _descToPoint(desc)
    attrs["Description"] = point
    return point, attrs


def _parseArrival(
    raw: dict[str, str],
    content: str,
    col_pos: dict[str, int],
) -> tuple[str, dict[str, str]]:
    attrs = {k: "" for k in ATTRS_ORDER}
    attrs["Type"] = "arrival"
    values, desc = _tailNNumericAndDesc(content, 1)
    if values:
        attrs["Time"] = values[0]
    point = _descToPoint(desc)
    attrs["Description"] = point
    return point, attrs


def _parseSlack(
    raw: dict[str, str],
    content: str,
    col_pos: dict[str, int],
) -> tuple[str, dict[str, str]]:
    attrs = {k: "" for k in ATTRS_ORDER}
    attrs["Type"] = "slack"
    values, desc = _tailNNumericAndDesc(content, 1)
    if values:
        attrs["Time"] = values[0]
    point = _descToPoint(desc)
    attrs["Description"] = point
    return point, attrs
