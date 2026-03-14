"""
parser_chaos Format2 单条 Path 解析器（最小实现）。

从 Format2 path 文本中解析 Path Start/Path End/slack 等 meta；
launch/capture 表格解析为简化实现，仅提取基本行信息，与 lib.parsers 完全独立。
完整 Format2 列（Type/Fanout/Cap/D-Trans/Trans/Derate/x-coord/y-coord 等）可在此基础上扩展。
"""
from __future__ import annotations

import re
from typing import Any

_RE_PATH_START = re.compile(
    r"^\s*Path Start\s+:\s+(.+?)\s+\(\s*flip-flop[^)]*,\s*(\w+)\s*\)\s*$"
)
_RE_PATH_END = re.compile(
    r"^\s*Path End\s+:\s+(.+?)\s+\(\s*flip-flop[^)]*,\s*(\w+)\s*\)\s*$"
)
_RE_SLACK_LINE = re.compile(r"slack\s*\((?:violated|met)\)", re.IGNORECASE)
_RE_SLACK_VALUE = re.compile(r"(-?\d+(?:\.\d+)?)\s+slack\s*\(", re.IGNORECASE)
_RE_SLACK_STATUS = re.compile(r"slack\s*\((\w+)\)", re.IGNORECASE)


def parseOnePath(path_id: int, path_text: str) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """
    解析单条 Format2 path 文本，返回 (meta, launch_rows, capture_rows)。

    逻辑：从 Path Start / Path End / slack 行提取 meta；当前为最小实现，
    launch_rows 与 capture_rows 返回空列表，仅保证流水线可运行。后续可在此补充完整表格解析。
    """
    lines = path_text.splitlines()
    meta = _defaultMeta(path_id)
    _fillMetaFromHeader(lines, meta)
    launch_rows: list[dict[str, Any]] = []
    capture_rows: list[dict[str, Any]] = []
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
    }


def _fillMetaFromHeader(lines: list[str], meta: dict[str, Any]) -> None:
    """从 Path Start / Path End / slack 行填充 meta。"""
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
