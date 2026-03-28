"""
parser_chaos：1 个分割器进程 + N 个 Worker + 队列；解析器与 extract 相同（parser_V2）。
"""
from __future__ import annotations

import csv
import os
from multiprocessing import Process, Queue
from pathlib import Path

from lib.extract import SEMANTIC_POINT_ATTRS
from lib.parser_V2.engine import create_timing_report_parser, detect_report_format
from lib.parser_V2.time_parser_base import TimeParser

from .. import log_util
from .aggregator import isResultSentinel, splitLaunchByCommonPin
from .constants import FORMAT1, TASK_SENTINEL
from .models import ParseOutput
from .splitter import runSplitterProcess
from .worker import runWorkerProcess

TASK_QUEUE_MAXSIZE = 256


def _csv_layout(format_key: str) -> tuple[list[str], list[str], list[str], str]:
    """与 extract.runExtract 相同的列集合与 delay 列名。"""
    p = create_timing_report_parser(format_key)
    semantic_attrs = list(dict.fromkeys(SEMANTIC_POINT_ATTRS + (p.attrs_order or [])))
    base_cols = p.point_base_columns + semantic_attrs
    launch_cols = p.point_base_columns + ["path_type"] + semantic_attrs
    delay_attr = "Incr" if "Incr" in p.attrs_order else "Delay"
    return base_cols, launch_cols, list(p.summary_columns), delay_attr


def runExtractChaos(
    report_path: str,
    output_dir: str,
    format_key: str,
    num_workers: int,
    paths_per_shard: int = 0,
    merge_launch: bool = False,
    log_level: str = "brief",
) -> int:
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

    _, _, _, delay_attr = _csv_layout(format_key)
    try:
        if int(paths_per_shard or 0) > 0:
            collectAndWriteSharded(
                result_queue=result_queue,
                num_workers=num_workers,
                output_dir=output_dir,
                format_key=format_key,
                delay_attr=delay_attr,
                paths_per_shard=int(paths_per_shard),
                merge_summary=True,
                merge_launch=bool(merge_launch),
            )
            log_util.brief(f"Sharded output enabled: {int(paths_per_shard)} path(s) per file")
            if merge_launch:
                log_util.full("Merged launch_path.csv enabled for sharded output")
        else:
            results = collectResults(result_queue, num_workers)
            if not results:
                log_util.error("No paths parsed.")
                return 0
            output = aggregateResultsLegacy(results, delay_attr=delay_attr)
            writeOutputCsv(output, output_dir, format_key)
    finally:
        splitter_proc.join()
        for w in workers:
            w.join()
    return 0


def collectResults(result_queue: Queue, num_workers: int) -> list:
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


def aggregateResultsLegacy(results: list, delay_attr: str) -> ParseOutput:
    from .aggregator import aggregateResults

    return aggregateResults(results, delay_attr=delay_attr)


def collectAndWriteSharded(
    result_queue: Queue,
    num_workers: int,
    output_dir: str,
    format_key: str,
    delay_attr: str,
    paths_per_shard: int,
    merge_summary: bool = True,
    merge_launch: bool = False,
) -> None:
    os.makedirs(output_dir, exist_ok=True)
    base_cols, launch_cols, summary_cols, _ = _csv_layout(format_key)

    shard_index = 1
    shard_paths: list[tuple[int, dict, list[dict], list[dict]]] = []
    end_count = 0
    total_paths = 0

    def _flushShard() -> None:
        nonlocal shard_index, shard_paths
        if not shard_paths:
            return
        shard_paths_sorted = sorted(shard_paths, key=lambda x: x[0])
        launch_rows: list[dict] = []
        capture_rows: list[dict] = []
        launch_clock_rows: list[dict] = []
        data_path_rows: list[dict] = []
        summary_rows: list[dict] = []

        for _path_id, meta, launch, capture in shard_paths_sorted:
            lc, dp, lc_n, dp_n, lc_delay, dp_delay = splitLaunchByCommonPin(
                launch, meta.get("startpoint", ""), delay_attr=delay_attr
            )
            meta["launch_clock_point_count"] = lc_n
            meta["data_path_point_count"] = dp_n
            meta["capture_point_count"] = len(capture)
            meta["launch_clock_delay"] = TimeParser._cleanMetricFloat(lc_delay)
            meta["data_path_delay"] = TimeParser._cleanMetricFloat(dp_delay)
            summary_rows.append(meta)
            launch_rows.extend(launch)
            capture_rows.extend(capture)
            launch_clock_rows.extend(lc)
            data_path_rows.extend(dp)

        suffix = f"_part{shard_index}.csv"
        _writeCsv(os.path.join(output_dir, f"launch_path{suffix}"), launch_rows, launch_cols)
        _writeCsv(os.path.join(output_dir, f"capture_path{suffix}"), capture_rows, base_cols)
        _writeCsv(os.path.join(output_dir, f"path_summary{suffix}"), summary_rows, summary_cols)
        _writeCsv(os.path.join(output_dir, f"launch_clock_path{suffix}"), launch_clock_rows, base_cols)
        _writeCsv(os.path.join(output_dir, f"data_path{suffix}"), data_path_rows, base_cols)

        shard_index += 1
        shard_paths = []

    while end_count < num_workers:
        item = result_queue.get()
        if isResultSentinel(item):
            end_count += 1
            continue
        if isinstance(item, Exception):
            raise item
        path_id, meta, launch, capture = item
        shard_paths.append((path_id, meta, launch, capture))
        total_paths += 1
        if paths_per_shard > 0 and len(shard_paths) >= paths_per_shard:
            _flushShard()

    _flushShard()

    if merge_summary:
        _mergeCsvParts(output_dir, "path_summary", merged_name="path_summary.csv")
    if merge_launch:
        _mergeCsvParts(output_dir, "launch_path", merged_name="launch_path.csv")

    log_util.brief(f"Wrote sharded outputs for {total_paths} path(s) -> {output_dir}")


def _mergeCsvParts(output_dir: str, base_name: str, merged_name: str | None = None) -> str:
    merged_name = merged_name or f"{base_name}.csv"
    out_path = str(Path(output_dir) / merged_name)
    parts = sorted(Path(output_dir).glob(f"{base_name}_part*.csv"))
    if not parts:
        return out_path
    writer = None
    with open(out_path, "w", encoding="utf-8-sig", newline="") as out_f:
        for i, p in enumerate(parts):
            with open(str(p), "r", encoding="utf-8-sig", newline="") as in_f:
                reader = csv.DictReader(in_f)
                if i == 0:
                    writer = csv.DictWriter(out_f, fieldnames=reader.fieldnames or [])
                    writer.writeheader()
                for row in reader:
                    writer.writerow(row)
    return out_path


def writeOutputCsv(output: ParseOutput, output_dir: str, format_key: str) -> None:
    os.makedirs(output_dir, exist_ok=True)
    base_cols, launch_cols, summary_cols, _ = _csv_layout(format_key)

    _writeCsv(os.path.join(output_dir, "launch_path.csv"), output.launch_rows, launch_cols)
    _writeCsv(os.path.join(output_dir, "capture_path.csv"), output.capture_rows, base_cols)
    _writeCsv(os.path.join(output_dir, "path_summary.csv"), output.summary_rows, summary_cols)
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
    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def detectFormatFromReport(report_path: str) -> str:
    with open(report_path, "r", encoding="utf-8", errors="replace") as f:
        peek = f.read(8192)
    return detect_report_format(peek or "")
