#!/usr/bin/env python3
"""
Parse APR Timing report (place_REG2REG.rpt): extract per-path Startpoint, Endpoint,
launch path / capture path points with Fanout, Cap, Trans; output launch_path.csv and capture_path.csv.
Supports multi-process parsing via --jobs N for large files.
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from multiprocessing import Pool, cpu_count
from typing import Any


# ---------------------------------------------------------------------------
# Report structure
# ---------------------------------------------------------------------------
RE_STARTPOINT = re.compile(r"^\s+Startpoint:\s+(.+?)\s+\(.+\)\s*$")
RE_ENDPOINT = re.compile(r"^\s+Endpoint:\s+(.+?)\s+\(.+\)\s*$")
RE_CLOCKED_BY = re.compile(r"clocked by (\w+)")
RE_SLACK = re.compile(r"^\s+slack\s+\((VIOLATED|MET)\)\s")
RE_SLACK_VALUE = re.compile(r"(-?\d+\.\d+)\s*$")
RE_POINT_HEADER = re.compile(r"^\s+Point\s+", re.IGNORECASE)
RE_SEP_LINE = re.compile(r"^\s+-{3,}\s*$")
RE_CLOCK_RISE = re.compile(r"^\s+clock\s+CPU_CLK\s+\(rise\s+edge\)\s")
RE_DATA_ARRIVAL = re.compile(r"^\s+data\s+arrival\s+time\s")
RE_LIBRARY_SETUP = re.compile(r"^\s+library\s+setup\s+time\s")

# PT 报告：时钟名任意 (如 clk_hclk)，library 为 setup 或 hold time
RE_CLOCK_RISE_PT = re.compile(r"^\s+clock\s+\S+\s+\(rise\s+edge\)\s")
RE_LIBRARY_SETUP_PT = re.compile(r"^\s+library\s+(setup|hold)\s+time\s")
# PT 报告：Startpoint/Endpoint 可能单独占一行（下一行为 clock 说明）
RE_STARTPOINT_PT = re.compile(r"^\s+Startpoint:\s+(.+?)\s*$")
RE_ENDPOINT_PT = re.compile(r"^\s+Endpoint:\s+(.+?)\s*$")


# 可配置的 Point 表指标列名，与报告表头一致；后续可扩展新指标
DEFAULT_POINT_METRICS = ["Fanout", "Cap", "Trans"]

# ---------------------------------------------------------------------------
# 格式扩展接口：按指定顺序解析属性，支持按 point 类型选用不同属性子集。
# 新增格式：增加 FORMATx_ATTRS_ORDER、FORMATx_SKIP_FIRST_ROWS、FORMATx_ATTRS_BY_TYPE，
# 并在 scan_path_blocks / parse_one_path 中分支；新增属性时加入 ATTRS_ORDER 与 ATTRS_BY_TYPE 即可。
# ---------------------------------------------------------------------------
OUTPUT_PIN_NAMES = frozenset({"Q", "Z", "ZN", "ZP"})

# Format1 (APR): Point 表列为 Fanout, Cap, Trans, Location, Incr, Path；前 2 行外按类型解析
FORMAT1_ATTRS_ORDER = ["Fanout", "Cap", "Trans", "Location", "Incr", "Path"]
FORMAT1_SKIP_FIRST_ROWS = 2
FORMAT1_ATTRS_BY_TYPE: dict[str, list[str]] = {
    "net": ["Fanout"],
    "input_pin": ["Cap", "Trans", "Location", "Incr", "Path"],
    "output_pin": ["Cap", "Trans", "Location", "Incr", "Path"],
}

# Format2: Type, Fanout, Cap, D-Trans, Trans, Derate, x-coord, y-coord, D-Delay, Delay, Time, Description；前 4 行外按类型解析
FORMAT2_ATTRS_ORDER = ["Type", "Fanout", "Cap", "D-Trans", "Trans", "Derate", "x-coord", "y-coord", "D-Delay", "Delay", "Time", "Description"]
FORMAT2_SKIP_FIRST_ROWS = 4
FORMAT2_ATTRS_BY_TYPE: dict[str, list[str]] = {
    "net": ["Fanout", "Cap"],
    "input_pin": ["D-Trans", "Trans", "Derate", "x-coord", "y-coord", "D-Delay", "Delay", "Time", "Description"],
    "output_pin": ["Trans", "Derate", "x-coord", "y-coord", "Delay", "Time", "Description"],
    "other": [],  # 由解析逻辑回退到 attrs_order 全量
}

# PT 报告：Point 表列为 Fanout, Cap, Trans, Derate, Incr, Path（无 Location）；前 2 行外按类型解析
FORMAT_PT_ATTRS_ORDER = ["Fanout", "Cap", "Trans", "Derate", "Incr", "Path"]
FORMAT_PT_SKIP_FIRST_ROWS = 2
FORMAT_PT_ATTRS_BY_TYPE: dict[str, list[str]] = {
    "net": ["Fanout", "Cap"],
    "input_pin": ["Trans", "Incr", "Path"],
    "output_pin": ["Trans", "Incr", "Path"],
}


def _point_type_format1(point_name: str) -> str:
    """Format1: 根据 point 名判断 net / input_pin / output_pin。"""
    if not point_name or "(net)" in point_name:
        return "net"
    m = re.search(r"/([A-Za-z0-9_\[\]]+)\s*\(?[A-Z]?", point_name)
    pin = m.group(1) if m else None
    if pin and pin in OUTPUT_PIN_NAMES:
        return "output_pin"
    return "input_pin"


def _point_type_format2(type_col: str, point_name: str) -> str:
    """Format2: Type 列 + Description 中 pin 名判断 net / input_pin / output_pin。"""
    if type_col and type_col.strip().lower() == "net":
        return "net"
    if type_col and type_col.strip().lower() == "pin":
        m = re.search(r"/([A-Za-z0-9_\[\]]+)\s*\(?[A-Z]?", point_name)
        pin = m.group(1) if m else None
        if pin and pin in OUTPUT_PIN_NAMES:
            return "output_pin"
        return "input_pin"
    return "other"

# 多格式支持：每种格式一套正则，便于兼容另一种 timing report
# 添加新格式：在 FORMAT_PATTERNS 中增加键（如 "pt"），并为其提供与 PATTERNS_APR 同结构的正则；
# 若另一种格式的 path 边界/表头/分节关键字不同，只需替换对应 re.Pattern。detect_format() 中可增加检测逻辑。
PATTERNS_APR = {
    "startpoint": RE_STARTPOINT,
    "endpoint": RE_ENDPOINT,
    "clocked_by": RE_CLOCKED_BY,
    "slack": RE_SLACK,
    "slack_value": RE_SLACK_VALUE,
    "point_header": RE_POINT_HEADER,
    "sep_line": RE_SEP_LINE,
    "clock_rise": RE_CLOCK_RISE,
    "data_arrival": RE_DATA_ARRIVAL,
    "library_setup": RE_LIBRARY_SETUP,
}
PATTERNS_PT = {
    **PATTERNS_APR,
    "startpoint": RE_STARTPOINT_PT,
    "endpoint": RE_ENDPOINT_PT,
    "clock_rise": RE_CLOCK_RISE_PT,
    "library_setup": RE_LIBRARY_SETUP_PT,
}
FORMAT_PATTERNS = {"apr": PATTERNS_APR, "pt": PATTERNS_PT}


def detect_format(peek_text: str) -> str:
    """根据文件开头内容检测报告格式。"""
    if not peek_text:
        return "apr"
    if "Path Start" in peek_text and "Path End" in peek_text and ("slack (VIOLATED" in peek_text or "slack (MET)" in peek_text):
        return "format2"
    if "Report : timing" in peek_text and "Derate" in peek_text and "Startpoint:" in peek_text:
        return "pt"
    if "Startpoint:" in peek_text and ("slack (VIOLATED" in peek_text or "slack (MET)" in peek_text):
        return "apr"
    return "apr"


# ---------------------------------------------------------------------------
# Format2：第二种报告格式（Path Start / Path End / Type-Fanout-Cap-Description 表）
# ---------------------------------------------------------------------------
RE_F2_PATH_START = re.compile(r"^\s*Path Start\s+:\s+(.+?)\s+\(\s*flip-flop[^)]*,\s*(\w+)\s*\)\s*$")
RE_F2_PATH_END = re.compile(r"^\s*Path End\s+:\s+(.+?)\s+\(\s*flip-flop[^)]*,\s*(\w+)\s*\)\s*$")
RE_F2_SLACK_VALUE = re.compile(r"(-?\d+\.\d+)\s+slack\s+\(")
RE_F2_SLACK_LINE = re.compile(r"slack\s+\((\w+)\)")
RE_F2_SEP = re.compile(r"^-=+\s*$")
RE_F2_DATA_ARRIVAL = re.compile(r"data arrival time")


def scan_path_blocks_format2(rpt_path: str) -> list[tuple[int, int, int, str]]:
    """Format2: 以 'Path Start' 为块起始，到含 'slack (VIOLATED)'/'slack (MET)' 的行结束。"""
    with open(rpt_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    blocks: list[tuple[int, int, int, str]] = []
    path_id = 0
    i = 0
    while i < len(lines):
        if RE_F2_PATH_START.match(lines[i]):
            start_i = i
            path_id += 1
            i += 1
            while i < len(lines):
                if RE_F2_PATH_START.match(lines[i]):
                    break
                if "slack (VIOLATED)" in lines[i] or "slack (MET)" in lines[i]:
                    i += 1
                    break
                i += 1
            block_text = "".join(lines[start_i:i])
            blocks.append((path_id, 0, 0, block_text))
            continue
        i += 1
    return blocks


def _column_positions_format2(header_line: str, attrs_list: list[str]) -> dict[str, int]:
    """Format2 表头：按 attrs_list 顺序查找列位置（Type, Fanout, Cap, D-Trans, Trans, Derate, x-coord, y-coord, D-Delay, Delay, Time, Description 等）。"""
    out: dict[str, int] = {}
    for name in attrs_list:
        idx = header_line.find(" " + name + " ")
        if idx >= 0:
            out[name] = idx
        else:
            idx = header_line.find(name)
            if idx >= 0:
                out[name] = idx
    return out


def _parse_point_line_format2(
    line: str,
    col_pos: dict[str, int],
    attrs_order: list[str],
    point_type_attrs: dict[str, list[str]],
    skip_first_n: int,
    segment_row_index: int,
) -> dict[str, Any]:
    """
    Format2 数据行：按 attrs_order 解析；Derate 保留原始值（如 0.900,0.900）；
    x-coord/y-coord 从 { x y } 中解析；前 skip_first_n 行保留全部属性，其余按 point 类型只保留对应属性。
    """
    s = line.rstrip()
    if not s.strip():
        return {}
    if not col_pos or "Description" not in col_pos:
        return {}
    ordered = sorted([n for n in attrs_order if n in col_pos], key=lambda n: col_pos[n])
    if not ordered:
        return {}
    desc_start = col_pos["Description"]
    point_raw = s[desc_start:].strip()
    if re.search(r"\s+/\s+", point_raw):
        point_raw = re.split(r"\s+/\s+", point_raw, maxsplit=1)[-1].strip()
    elif re.search(r"\s+\\\s+", point_raw):
        point_raw = re.split(r"\s+\\\s+", point_raw, maxsplit=1)[-1].strip()
    else:
        point_raw = re.sub(r"^[\s\d.-]+", "", point_raw).strip()
    point = point_raw.lstrip("/ \\").strip() if point_raw else ""
    result: dict[str, Any] = {"point": point, "Description": point}
    type_val = ""
    for i, name in enumerate(ordered):
        start = col_pos[name]
        end = col_pos[ordered[i + 1]] if i + 1 < len(ordered) else len(s)
        val = s[start:end].strip() if start < end else ""
        if name == "Type":
            type_val = val
        if name == "Description":
            continue
        if val == "-" or val == "-0.000":
            val = ""
        if name == "Derate":
            dm = re.search(r"(\d+\.\d+\s*,\s*\d+\.\d+)", s)
            result[name] = dm.group(1).replace(" ", "") if dm else val
            continue
        if name in ("x-coord", "y-coord"):
            continue
        result[name] = val
    brace = re.search(r"\{\s*([-\d.]+\s+[-\d.]+)\s*\}", s)
    if brace:
        parts = brace.group(1).split()
        result["x-coord"] = parts[0] if len(parts) >= 1 else ""
        result["y-coord"] = parts[1] if len(parts) >= 2 else ""
        rest = s[brace.end():]
        three = re.match(r"\s*(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+", rest)
        if three:
            result["D-Delay"] = three.group(1)
            result["Delay"] = three.group(2)
            result["Time"] = three.group(3)
        else:
            two = re.match(r"\s*(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+", rest)
            if two:
                result["D-Delay"] = ""
                result["Delay"] = two.group(1)
                result["Time"] = two.group(2)
    else:
        result["x-coord"] = ""
        result["y-coord"] = ""
    for a in attrs_order:
        if a not in result and a != "Description":
            result[a] = ""
    if segment_row_index >= skip_first_n:
        ptype = _point_type_format2(type_val, point)
        allowed = point_type_attrs.get(ptype) or attrs_order
        for a in attrs_order:
            if a != "Description" and a not in allowed:
                result[a] = ""
    return result


def parse_one_path_format2(path_id: int, path_text: str, metric_names: list[str]) -> tuple[dict[str, Any], list[dict], list[dict]]:
    """Format2: 解析 Path Start/Path End/slack，Type-Fanout-Cap-Description 表，launch 到 data arrival time，capture 到 -=-=- 前。"""
    lines = path_text.splitlines()
    meta: dict[str, Any] = {
        "path_id": path_id,
        "startpoint": "",
        "endpoint": "",
        "startpoint_clock": "",
        "endpoint_clock": "",
        "slack": "",
        "slack_status": "",
        "arrival_time": "",
        "required_time": "",
        "trans": "",
        "cap": "",
    }
    launch_rows: list[dict[str, Any]] = []
    capture_rows: list[dict[str, Any]] = []

    for line in lines:
        m = RE_F2_PATH_START.match(line)
        if m:
            meta["startpoint"] = m.group(1).strip()
            meta["startpoint_clock"] = m.group(2).strip()
            continue
        m = RE_F2_PATH_END.match(line)
        if m:
            meta["endpoint"] = m.group(1).strip()
            meta["endpoint_clock"] = m.group(2).strip()
            continue
        if "slack (VIOLATED)" in line or "slack (MET)" in line:
            vm = RE_F2_SLACK_VALUE.search(line)
            sm = RE_F2_SLACK_LINE.search(line)
            if vm:
                meta["slack"] = vm.group(1).strip()
            if sm:
                meta["slack_status"] = sm.group(1).strip()
            break

    col_pos: dict[str, int] = {}
    table_start = 0
    attrs_order = FORMAT2_ATTRS_ORDER
    for idx in range(len(lines)):
        if "Type" in lines[idx] and "Fanout" in lines[idx] and "Cap" in lines[idx]:
            header_line = lines[idx]
            col_pos = _column_positions_format2(header_line, FORMAT2_ATTRS_ORDER)
            if "Description" in col_pos and any(a in col_pos for a in attrs_order):
                table_start = idx + 1
                if table_start < len(lines) and RE_F2_SEP.match(lines[table_start]):
                    table_start += 1
                break
            col_pos = {}

    in_launch = True
    in_capture = False
    for j in range(table_start, len(lines)):
        if RE_F2_SEP.match(lines[j]):
            if in_capture:
                break
            continue
        seg_idx = len(launch_rows) if in_launch else len(capture_rows)
        row = _parse_point_line_format2(
            lines[j], col_pos, attrs_order, FORMAT2_ATTRS_BY_TYPE, FORMAT2_SKIP_FIRST_ROWS, seg_idx
        )
        if not row or not row.get("point"):
            continue
        if RE_F2_DATA_ARRIVAL.search(lines[j]):
            if in_launch and launch_rows:
                meta["trans"] = launch_rows[-1].get("Trans", "")
                meta["cap"] = launch_rows[-1].get("Cap", "")
            if in_launch:
                vm = re.search(r"(-?\d+\.\d+)\s+data arrival time", lines[j])
                if vm:
                    meta["arrival_time"] = vm.group(1).strip()
            launch_rows.append({
                "path_id": path_id,
                "startpoint": meta["startpoint"],
                "endpoint": meta["endpoint"],
                "startpoint_clock": meta["startpoint_clock"],
                "endpoint_clock": meta["endpoint_clock"],
                "slack": meta["slack"],
                "slack_status": meta["slack_status"],
                "point_index": len(launch_rows) + 1,
                "point": row["point"],
                **{a: row.get(a, "") for a in attrs_order},
            })
            in_launch = False
            in_capture = True
            continue
        if in_launch:
            launch_rows.append({
                "path_id": path_id,
                "startpoint": meta["startpoint"],
                "endpoint": meta["endpoint"],
                "startpoint_clock": meta["startpoint_clock"],
                "endpoint_clock": meta["endpoint_clock"],
                "slack": meta["slack"],
                "slack_status": meta["slack_status"],
                "point_index": len(launch_rows) + 1,
                "point": row["point"],
                **{a: row.get(a, "") for a in attrs_order},
            })
        elif in_capture:
            capture_rows.append({
                "path_id": path_id,
                "startpoint": meta["startpoint"],
                "endpoint": meta["endpoint"],
                "startpoint_clock": meta["startpoint_clock"],
                "endpoint_clock": meta["endpoint_clock"],
                "slack": meta["slack"],
                "slack_status": meta["slack_status"],
                "point_index": len(capture_rows) + 1,
                "point": row["point"],
                **{a: row.get(a, "") for a in attrs_order},
            })

    for line in lines:
        if "data required time" in line:
            vm = re.search(r"(-?\d+\.\d+)\s+data required time", line)
            if vm:
                meta["required_time"] = vm.group(1).strip()
                break

    return (meta, launch_rows, capture_rows)


def _column_positions(header_line: str, attrs_list: list[str]) -> dict[str, int]:
    """Find start index of each attribute in the Point table header. attrs_list 为指定顺序的属性名列表（扩展接口）."""
    out: dict[str, int] = {}
    for name in attrs_list:
        idx = header_line.find(" " + name + " ")
        if idx >= 0:
            out[name] = idx
        else:
            idx = header_line.find(name)
            if idx >= 0:
                out[name] = idx
    return out


def _parse_point_line_format1(
    line: str,
    col_pos: dict[str, int],
    attrs_order: list[str],
    point_type_attrs: dict[str, list[str]],
    skip_first_n: int,
    segment_row_index: int,
) -> dict[str, Any]:
    """
    Format1 数据行：按 attrs_order 解析；前 skip_first_n 行保留全部属性，其余按 point 类型只保留对应属性。
    """
    s = line.rstrip()
    if not s.strip():
        return {}
    if not col_pos or not attrs_order:
        return {}
    ordered = sorted([n for n in attrs_order if n in col_pos], key=lambda n: col_pos[n])
    if not ordered:
        return {}
    first_start = col_pos[ordered[0]]
    point = s[:first_start].strip() if first_start else s.strip()
    result: dict[str, Any] = {"point": point}
    for i, name in enumerate(ordered):
        start = col_pos[name]
        end = col_pos[ordered[i + 1]] if i + 1 < len(ordered) else len(s)
        val = s[start:end].strip() if start < end else ""
        if val == "-":
            val = ""
        result[name] = val
    for a in attrs_order:
        if a not in result:
            result[a] = ""
    if segment_row_index >= skip_first_n:
        ptype = _point_type_format1(point)
        allowed = point_type_attrs.get(ptype, attrs_order)
        for a in attrs_order:
            if a not in allowed:
                result[a] = ""
    return result


def _parse_point_line(line: str, col_pos: dict[str, int], metric_names: list[str]) -> dict[str, Any]:
    """Parse one Point table line into point name and each configured metric."""
    s = line.rstrip()
    if not s.strip():
        return {}
    if col_pos and metric_names:
        # 按列起始位置排序，得到 [..., Location]
        ordered = sorted(
            [n for n in metric_names + ["Location"] if n in col_pos],
            key=lambda n: col_pos[n],
        )
        if not ordered:
            return {}
        first_start = col_pos[ordered[0]]
        point = s[:first_start].strip() if first_start else s.strip()
        result: dict[str, Any] = {"point": point}
        for i, name in enumerate(ordered):
            start = col_pos[name]
            end = col_pos[ordered[i + 1]] if i + 1 < len(ordered) else len(s)
            val = s[start:end].strip() if start < end else ""
            if name == "Location":
                continue
            if val == "-":
                val = ""
            result[name] = val
        for m in metric_names:
            if m not in result:
                result[m] = ""
        return result
    # Fallback: net line with only fanout at end
    fm = re.search(r"(\d+)\s*$", s)
    if fm:
        return {"point": s[: fm.start()].strip(), **{m: (fm.group(1) if m == "Fanout" else "") for m in metric_names}}
    return {"point": s.strip(), **{m: "" for m in metric_names}}


def parse_one_path(path_id: int, path_text: str, metric_names: list[str], format_key: str = "apr") -> tuple[dict[str, Any], list[dict], list[dict]]:
    """
    Parse a single timing path block. Returns (meta, launch_rows, capture_rows).
    format_key: 'apr' | 'pt' | 'format2'，决定使用哪套正则与分节规则。
    """
    if format_key == "format2":
        return parse_one_path_format2(path_id, path_text, metric_names)
    patterns = FORMAT_PATTERNS.get(format_key, PATTERNS_APR)
    lines = path_text.splitlines()
    meta: dict[str, Any] = {
        "path_id": path_id,
        "startpoint": "",
        "endpoint": "",
        "startpoint_clock": "",
        "endpoint_clock": "",
        "slack": "",
        "slack_status": "",
        "arrival_time": "",
        "required_time": "",
        "trans": "",
        "cap": "",
    }
    launch_rows: list[dict[str, Any]] = []
    capture_rows: list[dict[str, Any]] = []

    if format_key == "pt":
        attrs_order = FORMAT_PT_ATTRS_ORDER
        point_type_attrs = FORMAT_PT_ATTRS_BY_TYPE
        skip_first_n = FORMAT_PT_SKIP_FIRST_ROWS
    else:
        attrs_order = FORMAT1_ATTRS_ORDER
        point_type_attrs = FORMAT1_ATTRS_BY_TYPE
        skip_first_n = FORMAT1_SKIP_FIRST_ROWS

    for i, line in enumerate(lines):
        m = patterns["startpoint"].match(line)
        if m:
            meta["startpoint"] = m.group(1).strip()
            cm = patterns["clocked_by"].search(line)
            if not cm and format_key == "pt" and i + 1 < len(lines):
                cm = patterns["clocked_by"].search(lines[i + 1])
            meta["startpoint_clock"] = cm.group(1).strip() if cm else ""
            continue
        m = patterns["endpoint"].match(line)
        if m:
            meta["endpoint"] = m.group(1).strip()
            cm = patterns["clocked_by"].search(line)
            if not cm and format_key == "pt" and i + 1 < len(lines):
                cm = patterns["clocked_by"].search(lines[i + 1])
            meta["endpoint_clock"] = cm.group(1).strip() if cm else ""
            continue
        m = patterns["slack"].match(line)
        if m:
            meta["slack_status"] = m.group(1).strip()
            vm = patterns["slack_value"].search(line)
            meta["slack"] = vm.group(1).strip() if vm else ""
            break

    # Find Point table header and separator (first occurrence in block)
    col_pos: dict[str, int] = {}
    header_line = ""
    table_start = 0
    for idx in range(len(lines)):
        if patterns["point_header"].match(lines[idx]):
            header_line = lines[idx]
            col_pos = _column_positions(header_line, attrs_order)
            if format_key == "pt":
                table_ok = "Path" in col_pos and any(a in col_pos for a in attrs_order)
            else:
                table_ok = "Location" in col_pos and any(a in col_pos for a in attrs_order)
            if table_ok:
                table_start = idx + 1
                if table_start < len(lines) and patterns["sep_line"].match(lines[table_start]):
                    table_start += 1
                break
            col_pos = {}

    # Launch path: from first clock rise to data arrival time (inclusive)
    in_launch = False
    launch_start_idx = -1
    for j in range(table_start, len(lines)):
        if patterns["clock_rise"].match(lines[j]):
            in_launch = True
            launch_start_idx = j
            continue
        if in_launch and patterns["data_arrival"].match(lines[j]):
            if j > launch_start_idx:
                seg_idx = (j - 1) - launch_start_idx
                end_row = _parse_point_line_format1(
                    lines[j - 1], col_pos, attrs_order, point_type_attrs, skip_first_n, seg_idx
                )
                if end_row:
                    meta["trans"] = end_row.get("Trans", "")
                    meta["cap"] = end_row.get("Cap", "")
            for k in range(launch_start_idx, j + 1):
                seg_idx = k - launch_start_idx
                row = _parse_point_line_format1(
                    lines[k], col_pos, attrs_order, point_type_attrs, skip_first_n, seg_idx
                )
                if row and row.get("point"):
                    launch_rows.append({
                        "path_id": path_id,
                        "startpoint": meta["startpoint"],
                        "endpoint": meta["endpoint"],
                        "startpoint_clock": meta["startpoint_clock"],
                        "endpoint_clock": meta["endpoint_clock"],
                        "slack": meta["slack"],
                        "slack_status": meta["slack_status"],
                        "point_index": len(launch_rows) + 1,
                        "point": row["point"],
                        **{a: row.get(a, "") for a in attrs_order},
                    })
            # arrival time: 该行末尾 Path 累计值；trans/cap 已从上一行 endpoint 取过
            vm = re.search(r"(-?\d+\.\d+)\s*$", lines[j])
            if vm:
                meta["arrival_time"] = vm.group(1).strip()
            break

    # Capture path: after data arrival, from next clock rise to before library setup time
    after_data_arrival = False
    in_capture = False
    capture_start_idx = -1
    for j in range(table_start, len(lines)):
        if patterns["data_arrival"].match(lines[j]):
            after_data_arrival = True
            continue
        if after_data_arrival and patterns["clock_rise"].match(lines[j]):
            in_capture = True
            capture_start_idx = j
            continue
        if in_capture and patterns["library_setup"].match(lines[j]):
            for k in range(capture_start_idx, j):
                seg_idx = k - capture_start_idx
                row = _parse_point_line_format1(
                    lines[k], col_pos, attrs_order, point_type_attrs, skip_first_n, seg_idx
                )
                if row and row.get("point"):
                    capture_rows.append({
                        "path_id": path_id,
                        "startpoint": meta["startpoint"],
                        "endpoint": meta["endpoint"],
                        "startpoint_clock": meta["startpoint_clock"],
                        "endpoint_clock": meta["endpoint_clock"],
                        "slack": meta["slack"],
                        "slack_status": meta["slack_status"],
                        "point_index": len(capture_rows) + 1,
                        "point": row["point"],
                        **{a: row.get(a, "") for a in attrs_order},
                    })
            break

    # required time: 块内首次出现 "data required time" 且带数字的行
    for line in lines:
        if "data required time" in line:
            vm = re.search(r"(-?\d+\.\d+)\s*$", line)
            if vm:
                meta["required_time"] = vm.group(1).strip()
                break

    # Format1 补漏：若 launch 段未解析到 arrival_time，在整块内查找 "data arrival time" 行并取行末数字
    if not meta.get("arrival_time"):
        for line in lines:
            if "data arrival time" in line:
                vm = re.search(r"(-?\d+\.\d+)\s*$", line)
                if vm:
                    meta["arrival_time"] = vm.group(1).strip()
                    break

    return (meta, launch_rows, capture_rows)


def scan_path_blocks(rpt_path: str, format_key: str = "apr") -> list[tuple[int, int, int, str]]:
    """
    Single-pass scan: read file and split into path blocks.
    format_key 决定用哪套正则识别 path 边界（Startpoint / slack 或 Path Start / slack）。
    Returns list of (path_id, 0, 0, path_text) for each timing path.
    """
    if format_key == "format2":
        return scan_path_blocks_format2(rpt_path)
    patterns = FORMAT_PATTERNS.get(format_key, PATTERNS_APR)
    with open(rpt_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    lines = content.splitlines()
    blocks: list[tuple[int, int, int, str]] = []
    path_id = 0
    i = 0
    while i < len(lines):
        if patterns["startpoint"].match(lines[i]):
            start_i = i
            path_id += 1
            i += 1
            while i < len(lines):
                if patterns["startpoint"].match(lines[i]):
                    break
                if patterns["slack"].match(lines[i]):
                    i += 1
                    break
                i += 1
            block_text = "\n".join(lines[start_i:i])
            blocks.append((path_id, 0, 0, block_text))
            continue
        i += 1
    return blocks


def _worker_parse(args: tuple) -> tuple[dict, list, list]:
    """Worker: parse one path block. args = (path_id, path_text, metric_names, format_key)."""
    path_id, path_text, metric_names, format_key = args
    meta, launch_rows, capture_rows = parse_one_path(path_id, path_text, metric_names, format_key)
    return (meta, launch_rows, capture_rows)


def run_single_process(path_blocks: list[tuple[int, int, int, str]], metric_names: list[str], format_key: str = "apr") -> tuple[list[dict], list[dict], list[dict]]:
    """Parse all blocks in the main process. Returns (all_launch, all_capture, all_meta)."""
    all_launch: list[dict] = []
    all_capture: list[dict] = []
    all_meta: list[dict] = []
    for (path_id, _, _, text) in path_blocks:
        meta, launch_rows, capture_rows = parse_one_path(path_id, text, metric_names, format_key)
        all_launch.extend(launch_rows)
        all_capture.extend(capture_rows)
        all_meta.append(meta)
    return (all_launch, all_capture, all_meta)


def run_multi_process(path_blocks: list[tuple[int, int, int, str]], jobs: int, metric_names: list[str], format_key: str = "apr") -> tuple[list[dict], list[dict], list[dict]]:
    """Distribute path blocks across workers. Returns (all_launch, all_capture, all_meta)."""
    args_list = [(pid, text, metric_names, format_key) for (pid, _, _, text) in path_blocks]
    with Pool(processes=jobs) as pool:
        results = pool.map(_worker_parse, args_list)
    all_launch: list[dict] = []
    all_capture: list[dict] = []
    all_meta: list[dict] = []
    for (_meta, launch_rows, capture_rows) in results:
        all_launch.extend(launch_rows)
        all_capture.extend(capture_rows)
        all_meta.append(_meta)
    return (all_launch, all_capture, all_meta)


def write_csv(out_path: str, rows: list[dict], columns: list[str]) -> None:
    """Write rows to CSV with given column order."""
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir) if os.path.basename(script_dir) == "scripts" else script_dir
    default_input = os.path.join(project_root, "input", "place_REG2REG.rpt")
    default_output = os.path.join(project_root, "output")

    parser = argparse.ArgumentParser(description="Parse APR Timing report to launch_path.csv and capture_path.csv")
    parser.add_argument(
        "input_rpt",
        nargs="?",
        default=default_input,
        help="Path to place_REG2REG.rpt",
    )
    parser.add_argument(
        "-o", "--output-dir",
        default=default_output,
        help="Output directory for CSV files",
    )
    parser.add_argument(
        "-j", "--jobs",
        type=int,
        default=1,
        metavar="N",
        help="Number of parallel workers (default 1). Use >1 for large files.",
    )
    parser.add_argument(
        "--metrics",
        nargs="*",
        default=None,
        metavar="NAME",
        help="Point table metric column names (default: Fanout Cap Trans). Example: --metrics Fanout Cap Trans",
    )
    parser.add_argument(
        "--format",
        choices=["apr", "pt", "format2", "auto"],
        default="auto",
        help="Report format: apr (APR 报告), pt (占位), format2 (Path Start/Path End 表), auto (默认)",
    )
    args = parser.parse_args()

    metric_names = args.metrics if args.metrics is not None else DEFAULT_POINT_METRICS.copy()
    print(f"Point metrics: {', '.join(metric_names)}")

    rpt_path = os.path.abspath(args.input_rpt)
    out_dir = os.path.abspath(args.output_dir)
    if not os.path.isfile(rpt_path):
        print(f"Error: input file not found: {rpt_path}", file=sys.stderr)
        return 1

    format_key = args.format
    if format_key == "auto":
        with open(rpt_path, "r", encoding="utf-8", errors="replace") as f:
            format_key = detect_format(f.read(8000))
        print(f"Format: {format_key} (auto-detected)")
    else:
        print(f"Format: {format_key}")

    print(f"Scanning: {rpt_path}")
    path_blocks = scan_path_blocks(rpt_path, format_key)
    # path_blocks from scan: list of (path_id, 0, 0, path_text) — we used 4-tuple for consistency
    if not path_blocks:
        print("No timing paths found.", file=sys.stderr)
        return 0

    n_paths = len(path_blocks)
    print(f"Found {n_paths} timing path(s).")

    jobs = args.jobs
    if jobs <= 0:
        jobs = max(1, cpu_count() - 1)
    if jobs > 1 and n_paths < 100:
        jobs = 1
        print("Using single process (path count < 100).")
    elif jobs > 1:
        print(f"Parsing with {jobs} workers.")

    if jobs <= 1:
        all_launch, all_capture, all_meta = run_single_process(path_blocks, metric_names, format_key)
    else:
        all_launch, all_capture, all_meta = run_multi_process(path_blocks, jobs, metric_names, format_key)

    base_cols = ["path_id", "startpoint", "endpoint", "startpoint_clock", "endpoint_clock", "slack", "slack_status", "point_index", "point"]
    attrs_for_csv = FORMAT1_ATTRS_ORDER if format_key == "apr" else (FORMAT2_ATTRS_ORDER if format_key == "format2" else (FORMAT_PT_ATTRS_ORDER if format_key == "pt" else metric_names))
    columns = base_cols + attrs_for_csv
    launch_path = os.path.join(out_dir, "launch_path.csv")
    capture_path = os.path.join(out_dir, "capture_path.csv")
    summary_path = os.path.join(out_dir, "path_summary.csv")

    write_csv(launch_path, all_launch, columns)
    write_csv(capture_path, all_capture, columns)

    summary_columns = ["path_id", "startpoint", "endpoint", "arrival_time", "required_time", "slack"]
    write_csv(summary_path, all_meta, summary_columns)

    print(f"Wrote {len(all_launch)} launch path rows -> {launch_path}")
    print(f"Wrote {len(all_capture)} capture path rows -> {capture_path}")
    print(f"Wrote {len(all_meta)} path summary rows -> {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
