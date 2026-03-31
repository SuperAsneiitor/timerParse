"""
解析 Timing 报告并输出多 CSV（extract 子命令逻辑）。

职责：根据输入报告与格式调用解析器，单/多进程解析后按 path 合并 launch/capture/summary，
并对每条 path 的 launch 按 startpoint 拆分为 launch_clock 与 data_path，最后写出 CSV。
不包含解析器实现，仅编排 parseReport/parseWithJobs 与写文件。
"""
from __future__ import annotations

import csv
import os
from pathlib import Path

from . import log_util
from .parser.engine import create_timing_report_parser, detect_report_format
from .parser.time_parser_base import ParseOutput, TimeParser

# 抽取结果中保留的语义列（与格式无关的统一列集合）
SEMANTIC_POINT_ATTRS = [
    "Type",
    "Fanout",
    "Cap",
    "D-Trans",
    "Delta",
    "Trans",
    "Derate",
    "DerateA",
    "DerateB",
    "TransMean",
    "TransSensit",
    "TransValue",
    "IncrMean",
    "IncrSensit",
    "IncrValue",
    "PathMean",
    "PathSensit",
    "PathValue",
    "Mean",
    "Sensit",
    "x-coord",
    "y-coord",
    "D-Delay",
    "Delay",
    "Incr",
    "Time",
    "Path",
    "trigger_edge",
    "Description",
]


def _workerParseOne(args: tuple) -> tuple:
    """多进程 worker：解析单条 path 文本，返回 (meta, launch_rows, capture_rows)。"""
    parser_cls, path_id, path_text = args
    parser = parser_cls()
    meta, launch, capture = parser.parseOnePath(path_id, path_text)
    return path_id, meta, launch, capture


def _mergeCsvParts(
    output_dir: str,
    base_name: str,
    merged_name: str | None = None,
) -> str:
    """将同目录下 base_name_part*.csv 合并为单个 CSV，并返回合并后的路径。"""
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


def parseWithJobs(
    parser_impl: TimeParser,
    report_path: str,
    jobs: int,
) -> ParseOutput:
    """
    按 jobs 数单进程或多进程解析报告。

    若 blocks 少于 100 或 jobs==1 则直接调用 parser.parseReport；否则多进程并行
    解析每块后合并，并对每条 path 的 launch 按 startpoint 拆分。
    """
    from multiprocessing import Pool, cpu_count
    from typing import Tuple

    blocks = parser_impl.scanPathBlocks(report_path)
    if not blocks:
        return ParseOutput([], [], [], [], [])

    if jobs <= 0:
        jobs = max(1, cpu_count() - 1)
    if jobs == 1 or len(blocks) < 100:
        return parser_impl.parseReport(report_path)

    parser_cls = parser_impl.__class__
    args_list = [(parser_cls, path_id, path_text) for (path_id, path_text) in blocks]
    with Pool(processes=jobs) as pool:
        results: list[Tuple[int, dict, list, list]] = pool.map(_workerParseOne, args_list)

    launch_rows = []
    capture_rows = []
    launch_clock_rows = []
    data_path_rows = []
    summary_rows = []
    delay_attr = "Incr" if "Incr" in parser_impl.attrs_order else "Delay"
    for _path_id, meta, launch, capture in results:
        lc, dp, lc_n, dp_n, lc_delay, dp_delay = parser_impl.splitLaunchByCommonPin(
            launch, meta.get("startpoint", ""), delay_attr=delay_attr
        )
        meta["launch_clock_point_count"] = lc_n
        meta["data_path_point_count"] = dp_n
        meta["capture_point_count"] = len(capture)
        meta["launch_clock_delay"] = parser_impl._cleanMetricFloat(lc_delay)
        meta["data_path_delay"] = parser_impl._cleanMetricFloat(dp_delay)
        summary_rows.append(meta)
        launch_rows.extend(launch)
        launch_clock_rows.extend(lc)
        data_path_rows.extend(dp)
        capture_rows.extend(capture)
    return ParseOutput(
        launch_rows,
        capture_rows,
        summary_rows,
        launch_clock_rows,
        data_path_rows,
    )


def parseWithJobsSharded(
    parser_impl: TimeParser,
    report_path: str,
    jobs: int,
    output_dir: str,
    paths_per_shard: int,
    merge_summary: bool = True,
    merge_launch: bool = False,
) -> int:
    """按 path 数分片解析并写出 CSV；可选在末尾合并 summary/launch。"""
    import csv
    from multiprocessing import Pool, cpu_count

    blocks = parser_impl.scanPathBlocks(report_path)
    if not blocks:
        return 0

    if paths_per_shard <= 0:
        paths_per_shard = 0

    if jobs <= 0:
        jobs = max(1, cpu_count() - 1)

    parser_cls = parser_impl.__class__
    args_list = [(parser_cls, path_id, path_text) for (path_id, path_text) in blocks]

    semantic_attrs = list(dict.fromkeys(SEMANTIC_POINT_ATTRS + (parser_impl.attrs_order or [])))
    base_cols = parser_impl.point_base_columns + semantic_attrs
    launch_cols = parser_impl.point_base_columns + ["path_type"] + semantic_attrs
    summary_cols = parser_impl.summary_columns

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    delay_attr = "Incr" if "Incr" in parser_impl.attrs_order else "Delay"
    shard_index = 1
    shard_path_count = 0

    launch_rows: list[dict] = []
    capture_rows: list[dict] = []
    launch_clock_rows: list[dict] = []
    data_path_rows: list[dict] = []
    summary_rows: list[dict] = []

    def _flushShard() -> None:
        nonlocal shard_index, shard_path_count
        if shard_path_count <= 0:
            return
        suffix = f"_part{shard_index}.csv"
        parser_impl.writeCsv(str(Path(output_dir) / f"launch_path{suffix}"), launch_rows, launch_cols)
        parser_impl.writeCsv(str(Path(output_dir) / f"capture_path{suffix}"), capture_rows, base_cols)
        parser_impl.writeCsv(str(Path(output_dir) / f"launch_clock_path{suffix}"), launch_clock_rows, base_cols)
        parser_impl.writeCsv(str(Path(output_dir) / f"data_path{suffix}"), data_path_rows, base_cols)
        parser_impl.writeCsv(str(Path(output_dir) / f"path_summary{suffix}"), summary_rows, summary_cols)

        shard_index += 1
        shard_path_count = 0
        launch_rows.clear()
        capture_rows.clear()
        launch_clock_rows.clear()
        data_path_rows.clear()
        summary_rows.clear()

    if jobs <= 1 or len(blocks) < 100:
        # 单进程：按 blocks 顺序解析并分片写出
        parser_single = parser_cls()
        for path_id, path_text in blocks:
            meta, launch, capture = parser_single.parseOnePath(path_id, path_text)
            lc, dp, lc_n, dp_n, lc_delay, dp_delay = parser_single.splitLaunchByCommonPin(
                launch, meta.get("startpoint", ""), delay_attr=delay_attr
            )
            meta["launch_clock_point_count"] = lc_n
            meta["data_path_point_count"] = dp_n
            meta["capture_point_count"] = len(capture)
            meta["launch_clock_delay"] = parser_single._cleanMetricFloat(lc_delay)
            meta["data_path_delay"] = parser_single._cleanMetricFloat(dp_delay)
            summary_rows.append(meta)
            launch_rows.extend(launch)
            launch_clock_rows.extend(lc)
            data_path_rows.extend(dp)
            capture_rows.extend(capture)
            shard_path_count += 1
            if paths_per_shard > 0 and shard_path_count >= paths_per_shard:
                _flushShard()
    else:
        # 多进程：使用 imap（按输入顺序输出），保证按 path 顺序做分片
        with Pool(processes=jobs) as pool:
            for path_id, meta, launch, capture in pool.imap(_workerParseOne, args_list):
                lc, dp, lc_n, dp_n, lc_delay, dp_delay = parser_impl.splitLaunchByCommonPin(
                    launch, meta.get("startpoint", ""), delay_attr=delay_attr
                )
                meta["launch_clock_point_count"] = lc_n
                meta["data_path_point_count"] = dp_n
                meta["capture_point_count"] = len(capture)
                meta["launch_clock_delay"] = parser_impl._cleanMetricFloat(lc_delay)
                meta["data_path_delay"] = parser_impl._cleanMetricFloat(dp_delay)
                summary_rows.append(meta)
                launch_rows.extend(launch)
                launch_clock_rows.extend(lc)
                data_path_rows.extend(dp)
                capture_rows.extend(capture)
                shard_path_count += 1
                if paths_per_shard > 0 and shard_path_count >= paths_per_shard:
                    _flushShard()

    _flushShard()

    if merge_summary:
        _mergeCsvParts(output_dir, "path_summary", merged_name="path_summary.csv")
    if merge_launch:
        _mergeCsvParts(output_dir, "launch_path", merged_name="launch_path.csv")

    return 0


def runExtract(args) -> int:
    """
    执行 extract 子命令：解析 timing 报告并写出 CSV。

    args 需包含 input_rpt, output_dir, format, jobs。
    若 format 为 auto，则根据报告内容 detect_report_format；否则使用指定格式创建解析器。
    """
    rpt_path = os.path.abspath(args.input_rpt)
    out_dir = os.path.abspath(args.output_dir)
    if not os.path.isfile(rpt_path):
        log_util.error(f"Error: input file not found: {rpt_path}")
        return 1

    format_key = args.format
    if format_key == "auto":
        with open(rpt_path, "r", encoding="utf-8", errors="replace") as f:
            format_key = detect_report_format(f.read())
        log_util.brief(f"Format: {format_key} (auto-detected)")
    else:
        log_util.brief(f"Format: {format_key}")

    parser_impl = create_timing_report_parser(format_key)
    paths_per_shard = int(getattr(args, "paths_per_shard", 0) or 0)
    merge_launch = bool(getattr(args, "merge_launch", False))
    if paths_per_shard > 0:
        rc = parseWithJobsSharded(
            parser_impl,
            rpt_path,
            jobs=args.jobs,
            output_dir=out_dir,
            paths_per_shard=paths_per_shard,
            merge_summary=True,
            merge_launch=merge_launch,
        )
        if rc != 0:
            return rc
        log_util.brief(f"Sharded output enabled: {paths_per_shard} path(s) per file")
        if merge_launch:
            log_util.full("Merged launch_path.csv enabled for sharded output")
        return 0

    result = parseWithJobs(parser_impl, rpt_path, jobs=args.jobs)

    launch_csv = os.path.join(out_dir, "launch_path.csv")
    capture_csv = os.path.join(out_dir, "capture_path.csv")
    summary_csv = os.path.join(out_dir, "path_summary.csv")
    launch_clock_csv = os.path.join(out_dir, "launch_clock_path.csv")
    data_path_csv = os.path.join(out_dir, "data_path.csv")

    semantic_attrs = list(dict.fromkeys(SEMANTIC_POINT_ATTRS + (parser_impl.attrs_order or [])))
    base_cols = parser_impl.point_base_columns + semantic_attrs
    launch_cols = parser_impl.point_base_columns + ["path_type"] + semantic_attrs
    parser_impl.writeCsv(launch_csv, result.launch_rows, launch_cols)
    parser_impl.writeCsv(capture_csv, result.capture_rows, base_cols)
    parser_impl.writeCsv(summary_csv, result.summary_rows, parser_impl.summary_columns)
    parser_impl.writeCsv(launch_clock_csv, result.launch_clock_rows, base_cols)
    parser_impl.writeCsv(data_path_csv, result.data_path_rows, base_cols)

    n_launch, n_capture, n_summary = len(result.launch_rows), len(result.capture_rows), len(result.summary_rows)
    n_lc, n_dp = len(result.launch_clock_rows), len(result.data_path_rows)
    log_util.brief(
        f"Wrote {n_launch} launch, {n_capture} capture, {n_summary} summary, {n_lc} launch_clock, {n_dp} data_path rows -> {out_dir}"
    )
    log_util.full(f"  {launch_csv} -> {n_launch} rows")
    log_util.full(f"  {capture_csv} -> {n_capture} rows")
    log_util.full(f"  {summary_csv} -> {n_summary} rows")
    log_util.full(f"  {launch_clock_csv} -> {n_lc} rows")
    log_util.full(f"  {data_path_csv} -> {n_dp} rows")
    return 0
