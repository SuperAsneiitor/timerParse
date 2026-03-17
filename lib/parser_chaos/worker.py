"""
parser_chaos 解析器 Worker 进程。

职责：从 task_queue 中取 (path_id, path_text)，根据 format_key 调用对应格式的解析函数，
将 (path_id, meta, launch_rows, capture_rows) 放入 result_queue；收到结束哨兵后放入结果哨兵并退出。
与 lib.parsers 完全独立。
"""
from __future__ import annotations

from multiprocessing import Queue
from typing import Any

from .constants import FORMAT1, FORMAT_FORMAT2, FORMAT_PT, RESULT_SENTINEL, TASK_SENTINEL
from .parser_format1 import parseOnePath as parseOnePathFormat1
from .parser_format2 import parseOnePath as parseOnePathFormat2
from .parser_pt import parseOnePath as parseOnePathPt


def runWorkerProcess(
    task_queue: Queue,
    result_queue: Queue,
    format_key: str,
) -> None:
    """
    Worker 进程入口：循环从 task_queue 取任务，解析后放入 result_queue。

    逻辑：每次 get (path_id, path_text)；若为 TASK_SENTINEL 则向 result_queue 放入
    RESULT_SENTINEL 并退出；否则根据 format_key 调用对应 parseOnePath，将
    (path_id, meta, launch_rows, capture_rows) put 到 result_queue。解析异常时 put 异常对象。
    """
    parser_fn = getParserForFormat(format_key)
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
            meta, launch_rows, capture_rows = parser_fn(path_id, path_text)
            result_queue.put((path_id, meta, launch_rows, capture_rows))
        except Exception as e:
            result_queue.put(e)
            result_queue.put(RESULT_SENTINEL)
            return


def getParserForFormat(format_key: str):
    """
    根据格式键返回对应的单 path 解析函数。

    返回值为 parseOnePath(path_id, path_text) -> (meta, launch_rows, capture_rows)。
    """
    key = (format_key or "").strip().lower()
    if key == FORMAT1:
        return parseOnePathFormat1
    if key == FORMAT_FORMAT2:
        return parseOnePathFormat2
    if key == FORMAT_PT:
        return parseOnePathPt
    return parseOnePathFormat1


def _isTaskSentinel(item: Any) -> bool:
    """判断 task_queue 取出的项是否为结束哨兵。"""
    return item == TASK_SENTINEL
