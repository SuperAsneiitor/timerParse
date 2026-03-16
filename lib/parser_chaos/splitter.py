"""
parser_chaos 报告分割器（独立进程）。

职责：在单独进程中读取报告文件，按格式将报告切分为多条 Timing Path 文本块，
逐块放入 task_queue 供解析器进程消费；完成后放入结束哨兵。
与 lib.parsers 完全独立，不引用其任何代码。
"""
from __future__ import annotations

import re
from multiprocessing import Queue
from typing import Any

from .constants import FORMAT1, FORMAT_FORMAT2, FORMAT_PT, TASK_SENTINEL


def runSplitterProcess(
    report_path: str, format_key: str, task_queue: Queue, num_workers: int = 1
) -> None:
    """
    分割器进程入口：读报告并按格式切分，将 (path_id, path_text) 放入 task_queue。

    逻辑：根据 format_key 调用对应格式的切分函数，得到 (path_id, path_text) 列表后
    依次 put 到 task_queue；最后 put num_workers 个 TASK_SENTINEL，使每个 worker 都能结束。
    若读文件或切分异常，将异常 put 到队列后退出，由主进程处理。
    """
    try:
        blocks = splitReportIntoBlocks(report_path, format_key)
        for path_id, path_text in blocks:
            task_queue.put((path_id, path_text))
    except Exception as e:
        task_queue.put(e)
    finally:
        for _ in range(num_workers):
            task_queue.put(TASK_SENTINEL)


def splitReportIntoBlocks(report_path: str, format_key: str) -> list[tuple[int, str]]:
    """
    根据格式将报告文件切分为多条 path 块，返回 [(path_id, path_text), ...]。

    逻辑：统一将 format1 与 apr 视为同一格式；按 format_key 分发到
    _splitFormat1、_splitFormat2、_splitPt 之一，返回对应格式的 path 块列表。
    """
    key = (format_key or "").strip().lower()
    if key == FORMAT1:
        return _splitFormat1(report_path)
    if key == FORMAT_FORMAT2:
        return _splitFormat2(report_path)
    if key == FORMAT_PT:
        return _splitPt(report_path)
    return _splitFormat1(report_path)


def _splitFormat1(report_path: str) -> list[tuple[int, str]]:
    """
    Format1/APR 格式切分：按 "Startpoint:" 行识别每条 path 起始，到下一条 Startpoint 或 slack 行结束。
    """
    with open(report_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    re_startpoint = re.compile(r"^\s*Startpoint:")
    re_slack = re.compile(r"^\s*slack\s+\((VIOLATED|MET)\)(?:\s|$)")
    blocks: list[tuple[int, str]] = []
    i = 0
    path_id = 0
    while i < len(lines):
        if re_startpoint.match(lines[i]):
            start_i = i
            path_id += 1
            i += 1
            while i < len(lines):
                if re_startpoint.match(lines[i]):
                    break
                if re_slack.match(lines[i]):
                    i += 1
                    break
                i += 1
            blocks.append((path_id, "\n".join(lines[start_i:i])))
            continue
        i += 1
    return blocks


def _splitFormat2(report_path: str) -> list[tuple[int, str]]:
    """
    Format2 格式切分：按 "Path Start" 行识别每条 path 起始，到下一条 Path Start 或 slack (violated|met) 结束。
    """
    with open(report_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    re_path_start = re.compile(r"^\s*Path Start\s+:\s+(.+?)\s+\(\s*flip-flop[^)]*,\s*(\w+)\s*\)\s*$")
    re_slack_line = re.compile(r"slack\s*\((?:violated|met)\)", re.IGNORECASE)
    blocks: list[tuple[int, str]] = []
    i = 0
    path_id = 0
    while i < len(lines):
        if re_path_start.match(lines[i]):
            start_i = i
            path_id += 1
            i += 1
            while i < len(lines):
                if re_path_start.match(lines[i]):
                    break
                if re_slack_line.search(lines[i]):
                    i += 1
                    break
                i += 1
            blocks.append((path_id, "".join(lines[start_i:i])))
            continue
        i += 1
    return blocks


def _splitPt(report_path: str) -> list[tuple[int, str]]:
    """
    PT 格式切分：按 "Startpoint:" 行识别（PT 表头可能无括号），到下一条 Startpoint 或 slack 行结束。
    """
    with open(report_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    re_startpoint = re.compile(r"^\s+Startpoint:\s+(.+?)\s*$")
    re_slack = re.compile(r"^\s+slack\s+\((VIOLATED|MET)\)\s")
    blocks: list[tuple[int, str]] = []
    i = 0
    path_id = 0
    while i < len(lines):
        if re_startpoint.match(lines[i]):
            start_i = i
            path_id += 1
            i += 1
            while i < len(lines):
                if re_startpoint.match(lines[i]):
                    break
                if re_slack.match(lines[i]):
                    i += 1
                    break
                i += 1
            blocks.append((path_id, "\n".join(lines[start_i:i])))
            continue
        i += 1
    return blocks
