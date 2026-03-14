"""
解析 Timing 报告并输出多 CSV（extract 子命令逻辑）。

职责：根据输入报告与格式调用解析器，单/多进程解析后按 path 合并 launch/capture/summary，
并对每条 path 的 launch 按 startpoint 拆分为 launch_clock 与 data_path，最后写出 CSV。
不包含解析器实现，仅编排 parseReport/parseWithJobs 与写文件。
"""
from __future__ import annotations

import os
import sys

from . import createParser, detectReportFormat
from .parsers.time_parser_base import ParseOutput, TimeParser

# 抽取结果中保留的语义列（与格式无关的统一列集合）
SEMANTIC_POINT_ATTRS = [
    "Type",
    "Fanout",
    "Cap",
    "D-Trans",
    "Trans",
    "Derate",
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
    return meta, launch, capture


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
        results: list[Tuple[dict, list, list]] = pool.map(_workerParseOne, args_list)

    launch_rows = []
    capture_rows = []
    launch_clock_rows = []
    data_path_rows = []
    summary_rows = []
    delay_attr = "Incr" if "Incr" in parser_impl.attrs_order else "Delay"
    for meta, launch, capture in results:
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


def runExtract(args) -> int:
    """
    执行 extract 子命令：解析 timing 报告并写出 CSV。

    args 需包含 input_rpt, output_dir, format, jobs。
    若 format 为 auto，则根据报告内容 detectReportFormat；否则使用指定格式创建解析器。
    """
    rpt_path = os.path.abspath(args.input_rpt)
    out_dir = os.path.abspath(args.output_dir)
    if not os.path.isfile(rpt_path):
        print(f"Error: input file not found: {rpt_path}", file=sys.stderr)
        return 1

    format_key = args.format
    if format_key == "auto":
        with open(rpt_path, "r", encoding="utf-8", errors="replace") as f:
            format_key = detectReportFormat(f.read())
        print(f"Format: {format_key} (auto-detected)")
    else:
        print(f"Format: {format_key}")

    parser_impl = createParser(format_key)
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

    print(f"Wrote {len(result.launch_rows)} launch rows -> {launch_csv}")
    print(f"Wrote {len(result.capture_rows)} capture rows -> {capture_csv}")
    print(f"Wrote {len(result.summary_rows)} summary rows -> {summary_csv}")
    print(f"Wrote {len(result.launch_clock_rows)} launch clock rows -> {launch_clock_csv}")
    print(f"Wrote {len(result.data_path_rows)} data path rows -> {data_path_csv}")
    return 0
