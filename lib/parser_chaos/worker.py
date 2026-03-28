"""
parser_chaos Worker：从队列取 path 块，使用与 extract 相同的 parser_V2 解析器解析。
"""
from __future__ import annotations

from multiprocessing import Queue
from typing import Any

from lib.parser_V2.engine import create_timing_report_parser

from .constants import RESULT_SENTINEL, TASK_SENTINEL


def runWorkerProcess(
    task_queue: Queue,
    result_queue: Queue,
    format_key: str,
) -> None:
    """
    Worker 入口：为当前进程创建一次解析器实例，循环解析 task_queue 中的 (path_id, path_text)。
    """
    key = (format_key or "").strip().lower()
    parser_impl = create_timing_report_parser(key)
    while True:
        item = task_queue.get()
        if _isTaskSentinel(item):
            result_queue.put(RESULT_SENTINEL)
            return
        if isinstance(item, Exception):
            result_queue.put(item)
            result_queue.put(RESULT_SENTINEL)
            return
        path_id, path_text = item
        try:
            meta, launch_rows, capture_rows = parser_impl.parseOnePath(path_id, path_text)
            result_queue.put((path_id, meta, launch_rows, capture_rows))
        except Exception as e:
            result_queue.put(e)
            result_queue.put(RESULT_SENTINEL)
            return


def _isTaskSentinel(item: Any) -> bool:
    return item == TASK_SENTINEL
