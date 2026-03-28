"""
lib.parser 多进程抽取：1 个分割器进程 + N 个 Worker + 队列。

与 lib.extract 使用相同的 TimeParser（create_timing_report_parser），仅调度模型不同。
"""
from __future__ import annotations

import csv
import os
import re
from multiprocessing import Process, Queue
from pathlib import Path
from typing import Any

from .. import log_util
from ..extract import SEMANTIC_POINT_ATTRS
from .engine import create_timing_report_parser, detect_report_format
from .time_parser_base import ParseOutput, TimeParser

# 与 CLI --format 一致；apr 在入口处规范为 format1
FORMAT1 = "format1"
FORMAT_FORMAT2 = "format2"
FORMAT_PT = "pt"

TASK_SENTINEL = (None, None)
RESULT_SENTINEL = (None, None, None, None)
TASK_QUEUE_MAXSIZE = 256


def _csv_layout(format_key: str) -> tuple[list[str], list[str], list[str], str]:
    p = create_timing_report_parser(format_key)
    semantic_attrs = list(dict.fromkeys(SEMANTIC_POINT_ATTRS + (p.attrs_order or [])))
    base_cols = p.point_base_columns + semantic_attrs
    launch_cols = p.point_base_columns + ["path_type"] + semantic_attrs
    delay_attr = "Incr" if "Incr" in p.attrs_order else "Delay"
    return base_cols, launch_cols, list(p.summary_columns), delay_attr


def split_launch_by_common_pin(
    launch_rows: list[dict[str, Any]],
    startpoint: str,
    delay_attr: str = "Incr",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int, int, float, float]:
    return TimeParser.splitLaunchByCommonPin(launch_rows, startpoint, delay_attr=delay_attr)


def aggregate_parallel_results(
    results: list[tuple[int, dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]],
    delay_attr: str = "Incr",
) -> ParseOutput:
    results_sorted = sorted(results, key=lambda x: x[0])
    launch_rows: list[dict[str, Any]] = []
    capture_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    launch_clock_rows: list[dict[str, Any]] = []
    data_path_rows: list[dict[str, Any]] = []
    for _path_id, meta, launch, capture in results_sorted:
        lc, dp, lc_n, dp_n, lc_delay, dp_delay = split_launch_by_common_pin(
            launch, meta.get("startpoint", ""), delay_attr=delay_attr
        )
        meta["launch_clock_point_count"] = lc_n
        meta["data_path_point_count"] = dp_n
        meta["capture_point_count"] = len(capture)
        meta["launch_clock_delay"] = TimeParser._cleanMetricFloat(lc_delay)
        meta["data_path_delay"] = TimeParser._cleanMetricFloat(dp_delay)
        summary_rows.append(meta)
        launch_rows.extend(launch)
        launch_clock_rows.extend(lc)
        data_path_rows.extend(dp)
        capture_rows.extend(capture)
    return ParseOutput(
        launch_rows=launch_rows,
        capture_rows=capture_rows,
        summary_rows=summary_rows,
        launch_clock_rows=launch_clock_rows,
        data_path_rows=data_path_rows,
    )


def _is_result_sentinel(item: tuple) -> bool:
    return item == RESULT_SENTINEL


def run_splitter_process(
    report_path: str, format_key: str, task_queue: Queue, num_workers: int = 1
) -> None:
    try:
        blocks = split_report_into_blocks(report_path, format_key)
        for path_id, path_text in blocks:
            task_queue.put((path_id, path_text))
    except Exception as e:
        task_queue.put(e)
    finally:
        for _ in range(num_workers):
            task_queue.put(TASK_SENTINEL)


def split_report_into_blocks(report_path: str, format_key: str) -> list[tuple[int, str]]:
    key = (format_key or "").strip().lower()
    if key == FORMAT1:
        return _split_format1(report_path)
    if key == FORMAT_FORMAT2:
        return _split_format2(report_path)
    if key == FORMAT_PT:
        return _split_pt(report_path)
    return _split_format1(report_path)


def _split_format1(report_path: str) -> list[tuple[int, str]]:
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


def _split_format2(report_path: str) -> list[tuple[int, str]]:
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


def _split_pt(report_path: str) -> list[tuple[int, str]]:
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


def run_worker_process(task_queue: Queue, result_queue: Queue, format_key: str) -> None:
    key = (format_key or "").strip().lower()
    parser_impl = create_timing_report_parser(key)
    while True:
        item = task_queue.get()
        if item == TASK_SENTINEL:
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


def runExtractParallel(
    report_path: str,
    output_dir: str,
    format_key: str,
    num_workers: int,
    paths_per_shard: int = 0,
    merge_launch: bool = False,
    log_level: str = "brief",
) -> int:
    """
    多进程队列抽取：输出与 lib.extract.runExtract 相同的一组 CSV。

    返回 0 成功，1 失败（如输入文件不存在）。
    """
    log_util.set_level(log_level)
    report_path = os.path.abspath(report_path)
    output_dir = os.path.abspath(output_dir)
    if not os.path.isfile(report_path):
        log_util.error(f"Error: input file not found: {report_path}")
        return 1
    if format_key == "auto":
        format_key = detect_format_from_report_file(report_path)
        log_util.brief(f"Format: {format_key} (auto-detected)")
    else:
        log_util.brief(f"Format: {format_key}")
    if format_key == "apr":
        format_key = FORMAT1

    task_queue: Queue = Queue(maxsize=TASK_QUEUE_MAXSIZE)
    result_queue: Queue = Queue()

    splitter_proc = Process(
        target=run_splitter_process,
        args=(report_path, format_key, task_queue, num_workers),
    )
    splitter_proc.start()

    workers = [
        Process(target=run_worker_process, args=(task_queue, result_queue, format_key))
        for _ in range(num_workers)
    ]
    for w in workers:
        w.start()

    _, _, _, delay_attr = _csv_layout(format_key)
    try:
        if int(paths_per_shard or 0) > 0:
            _collect_and_write_sharded(
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
            results = _collect_results(result_queue, num_workers)
            if not results:
                log_util.error("No paths parsed.")
                return 0
            output = aggregate_parallel_results(results, delay_attr=delay_attr)
            _write_output_csv(output, output_dir, format_key)
    finally:
        splitter_proc.join()
        for w in workers:
            w.join()
    return 0


def _collect_results(result_queue: Queue, num_workers: int) -> list:
    results = []
    end_count = 0
    while end_count < num_workers:
        item = result_queue.get()
        if _is_result_sentinel(item):
            end_count += 1
            continue
        if isinstance(item, Exception):
            raise item
        results.append(item)
    return results


def _collect_and_write_sharded(
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

    def _flush_shard() -> None:
        nonlocal shard_index, shard_paths
        if not shard_paths:
            return
        shard_sorted = sorted(shard_paths, key=lambda x: x[0])
        launch_rows: list[dict] = []
        capture_rows: list[dict] = []
        launch_clock_rows: list[dict] = []
        data_path_rows: list[dict] = []
        summary_rows: list[dict] = []

        for _path_id, meta, launch, capture in shard_sorted:
            lc, dp, lc_n, dp_n, lc_delay, dp_delay = split_launch_by_common_pin(
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
        _write_csv(os.path.join(output_dir, f"launch_path{suffix}"), launch_rows, launch_cols)
        _write_csv(os.path.join(output_dir, f"capture_path{suffix}"), capture_rows, base_cols)
        _write_csv(os.path.join(output_dir, f"path_summary{suffix}"), summary_rows, summary_cols)
        _write_csv(os.path.join(output_dir, f"launch_clock_path{suffix}"), launch_clock_rows, base_cols)
        _write_csv(os.path.join(output_dir, f"data_path{suffix}"), data_path_rows, base_cols)

        shard_index += 1
        shard_paths = []

    while end_count < num_workers:
        item = result_queue.get()
        if _is_result_sentinel(item):
            end_count += 1
            continue
        if isinstance(item, Exception):
            raise item
        path_id, meta, launch, capture = item
        shard_paths.append((path_id, meta, launch, capture))
        total_paths += 1
        if paths_per_shard > 0 and len(shard_paths) >= paths_per_shard:
            _flush_shard()

    _flush_shard()

    if merge_summary:
        _merge_csv_parts(output_dir, "path_summary", merged_name="path_summary.csv")
    if merge_launch:
        _merge_csv_parts(output_dir, "launch_path", merged_name="launch_path.csv")

    log_util.brief(f"Wrote sharded outputs for {total_paths} path(s) -> {output_dir}")


def _merge_csv_parts(output_dir: str, base_name: str, merged_name: str | None = None) -> str:
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


def _write_output_csv(output: ParseOutput, output_dir: str, format_key: str) -> None:
    os.makedirs(output_dir, exist_ok=True)
    base_cols, launch_cols, summary_cols, _ = _csv_layout(format_key)

    _write_csv(os.path.join(output_dir, "launch_path.csv"), output.launch_rows, launch_cols)
    _write_csv(os.path.join(output_dir, "capture_path.csv"), output.capture_rows, base_cols)
    _write_csv(os.path.join(output_dir, "path_summary.csv"), output.summary_rows, summary_cols)
    _write_csv(os.path.join(output_dir, "launch_clock_path.csv"), output.launch_clock_rows, base_cols)
    _write_csv(os.path.join(output_dir, "data_path.csv"), output.data_path_rows, base_cols)

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


def _write_csv(output_path: str, rows: list[dict], columns: list[str]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def detect_format_from_report_file(report_path: str) -> str:
    with open(report_path, "r", encoding="utf-8", errors="replace") as f:
        peek = f.read(8192)
    return detect_report_format(peek or "")


# 兼容旧脚本 / 历史名称
runExtractChaos = runExtractParallel
detectFormatFromReport = detect_format_from_report_file

__all__ = [
    "FORMAT1",
    "FORMAT_FORMAT2",
    "FORMAT_PT",
    "TASK_SENTINEL",
    "RESULT_SENTINEL",
    "ParseOutput",
    "aggregate_parallel_results",
    "split_launch_by_common_pin",
    "split_report_into_blocks",
    "runExtractParallel",
    "runExtractChaos",
    "detect_format_from_report_file",
    "detectFormatFromReport",
]
