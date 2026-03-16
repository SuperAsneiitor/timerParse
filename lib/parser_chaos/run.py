"""
parser_chaos 流水线编排与入口。

职责：创建任务队列与结果队列，启动 1 个分割器进程与 N 个解析器 Worker 进程，
收集结果后聚合、写出 CSV。与 lib.parsers 及 lib.extract 完全独立。
"""
from __future__ import annotations

import csv
import os
import sys
from multiprocessing import Process, Queue

from .. import log_util
from .aggregator import aggregateResults, isResultSentinel
from .constants import (
    FORMAT1,
    FORMAT_FORMAT2,
    FORMAT_PT,
    POINT_BASE_COLUMNS,
    SEMANTIC_POINT_ATTRS,
    SUMMARY_COLUMNS,
)
from .models import ParseOutput
from .parser_format1 import ATTRS_ORDER as FORMAT1_ATTRS
from .parser_pt import ATTRS_ORDER as PT_ATTRS
from .splitter import runSplitterProcess
from .worker import runWorkerProcess

# 各格式点表列顺序（用于 CSV 表头）
_FORMAT_ATTRS = {
    FORMAT1: FORMAT1_ATTRS,
    FORMAT_PT: PT_ATTRS,
    FORMAT_FORMAT2: ["Type", "Fanout", "Cap", "D-Trans", "Trans", "Derate", "x-coord", "y-coord", "D-Delay", "Delay", "Time", "trigger_edge", "Description"],
}

# 各格式用于累加延迟的列名（launch_clock/data_path 段求和）
_DELAY_ATTR = {FORMAT1: "Incr", FORMAT_PT: "Incr", FORMAT_FORMAT2: "Delay"}

# 任务队列最大长度，避免分割器过快导致内存膨胀
TASK_QUEUE_MAXSIZE = 256


def runExtractChaos(
    report_path: str,
    output_dir: str,
    format_key: str,
    num_workers: int,
    log_level: str = "brief",
) -> int:
    """
    使用「1 个分割器 + N 个解析器」流水线执行报告解析并写出 CSV。

    逻辑：创建 task_queue、result_queue；启动 1 个分割器进程（读报告、切块、放入 task_queue），
    启动 num_workers 个 Worker 进程（从 task_queue 取块、解析、放入 result_queue）；主进程
    从 result_queue 收集直至收到 num_workers 个结束哨兵；按 path_id 排序后聚合，写出 5 个 CSV。
    若 format_key 为 auto，则根据报告内容检测格式。返回 0 成功，1 失败。
    """
    log_util.set_level(log_level)
    report_path = os.path.abspath(report_path)
    output_dir = os.path.abspath(output_dir)
    if not os.path.isfile(report_path):
        log_util.error(f"Error: input file not found: {report_path}")
        return 1
    if format_key == "auto":
        format_key = detectFormatFromReport(report_path)
        log_util.brief(f"Format: {format_key} (auto-detected)")
    else:
        log_util.brief(f"Format: {format_key}")
    # apr 与 format1 同一格式，统一为 format1
    if format_key == "apr":
        format_key = FORMAT1

    task_queue: Queue = Queue(maxsize=TASK_QUEUE_MAXSIZE)
    result_queue: Queue = Queue()

    splitter_proc = Process(
        target=runSplitterProcess,
        args=(report_path, format_key, task_queue, num_workers),
    )
    splitter_proc.start()

    workers = [
        Process(
            target=runWorkerProcess,
            args=(task_queue, result_queue, format_key),
        )
        for _ in range(num_workers)
    ]
    for w in workers:
        w.start()

    try:
        results = collectResults(result_queue, num_workers)
    finally:
        splitter_proc.join()
        for w in workers:
            w.join()

    if not results:
        log_util.error("No paths parsed.")
        return 0

    delay_attr = _DELAY_ATTR.get(format_key, "Incr")
    output = aggregateResults(results, delay_attr=delay_attr)
    writeOutputCsv(output, output_dir, format_key)
    return 0


def collectResults(result_queue: Queue, num_workers: int) -> list:
    """
    从 result_queue 收集解析结果，直到收到 num_workers 个结束哨兵。

    逻辑：循环 get()；若为结束哨兵则 end_count += 1，达到 num_workers 时返回；
    若为异常则抛出；否则将 (path_id, meta, launch, capture) 加入列表。
    """
    results = []
    end_count = 0
    while end_count < num_workers:
        item = result_queue.get()
        if isResultSentinel(item):
            end_count += 1
            continue
        if isinstance(item, Exception):
            raise item
        results.append(item)
    return results


def writeOutputCsv(output: ParseOutput, output_dir: str, format_key: str) -> None:
    """
    将 ParseOutput 按与现有 extract 相同的 5 个文件写出到 output_dir。

    文件：launch_path.csv（含 path_type）、capture_path.csv、path_summary.csv、
    launch_clock_path.csv、data_path.csv。列顺序由 POINT_BASE_COLUMNS、SUMMARY_COLUMNS 与格式属性列决定。
    """
    os.makedirs(output_dir, exist_ok=True)
    attrs_order = _FORMAT_ATTRS.get(format_key, FORMAT1_ATTRS)
    semantic_attrs = list(dict.fromkeys(SEMANTIC_POINT_ATTRS + attrs_order))
    base_cols = POINT_BASE_COLUMNS + semantic_attrs
    launch_cols = POINT_BASE_COLUMNS + ["path_type"] + semantic_attrs

    _writeCsv(os.path.join(output_dir, "launch_path.csv"), output.launch_rows, launch_cols)
    _writeCsv(os.path.join(output_dir, "capture_path.csv"), output.capture_rows, base_cols)
    _writeCsv(os.path.join(output_dir, "path_summary.csv"), output.summary_rows, SUMMARY_COLUMNS)
    _writeCsv(os.path.join(output_dir, "launch_clock_path.csv"), output.launch_clock_rows, base_cols)
    _writeCsv(os.path.join(output_dir, "data_path.csv"), output.data_path_rows, base_cols)

    n_launch = len(output.launch_rows)
    n_capture = len(output.capture_rows)
    n_summary = len(output.summary_rows)
    n_lc = len(output.launch_clock_rows)
    n_dp = len(output.data_path_rows)
    log_util.brief(
        f"Wrote {n_launch} launch, {n_capture} capture, {n_summary} summary, {n_lc} launch_clock, {n_dp} data_path rows -> {output_dir}"
    )
    log_util.full(f"  {output_dir}/launch_path.csv -> {n_launch} rows")
    log_util.full(f"  {output_dir}/capture_path.csv -> {n_capture} rows")
    log_util.full(f"  {output_dir}/path_summary.csv -> {n_summary} rows")
    log_util.full(f"  {output_dir}/launch_clock_path.csv -> {n_lc} rows")
    log_util.full(f"  {output_dir}/data_path.csv -> {n_dp} rows")


def _writeCsv(output_path: str, rows: list[dict], columns: list[str]) -> None:
    """将行数据按列顺序写出为 CSV（UTF-8 BOM）。"""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def detectFormatFromReport(report_path: str) -> str:
    """
    根据报告文件开头内容自动识别格式，返回 format1 / format2 / pt。

    逻辑：读前 8KB 文本，若含 "Path Start" 与 "Path End" 及 slack 则 format2；
    若含 "Report : timing" 与 "Derate" 与 "Startpoint:" 则 pt；否则 format1。
    """
    with open(report_path, "r", encoding="utf-8", errors="replace") as f:
        peek = f.read(8192)
    if not peek:
        return FORMAT1
    if "Path Start" in peek and "Path End" in peek and (
        "slack (VIOLATED" in peek or "slack (MET)" in peek
    ):
        return FORMAT_FORMAT2
    if "Report : timing" in peek and "Derate" in peek and "Startpoint:" in peek:
        return FORMAT_PT
    if "Startpoint:" in peek and ("slack (VIOLATED" in peek or "slack (MET)" in peek):
        return FORMAT1
    return FORMAT1
