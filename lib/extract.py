"""解析 Timing 报告 → 多 CSV（extract 子命令逻辑）。"""
from __future__ import annotations

import os
import sys

from . import create_parser, detect_report_format
from .parsers.time_parser_base import ParseOutput, TimeParser


def _worker_parse_one(args: tuple) -> tuple:
    parser_cls, path_id, path_text = args
    parser = parser_cls()
    meta, launch, capture = parser.parse_one_path(path_id, path_text)
    return meta, launch, capture


def parse_with_jobs(
    parser_impl: TimeParser,
    report_path: str,
    jobs: int,
) -> ParseOutput:
    from multiprocessing import Pool, cpu_count
    from typing import Tuple

    blocks = parser_impl.scan_path_blocks(report_path)
    if not blocks:
        return ParseOutput([], [], [], [], [])

    if jobs <= 0:
        jobs = max(1, cpu_count() - 1)
    if jobs == 1 or len(blocks) < 100:
        return parser_impl.parse_report(report_path)

    parser_cls = parser_impl.__class__
    args_list = [(parser_cls, path_id, path_text) for (path_id, path_text) in blocks]
    with Pool(processes=jobs) as pool:
        results: list[Tuple[dict, list, list]] = pool.map(_worker_parse_one, args_list)

    launch_rows = []
    capture_rows = []
    launch_clock_rows = []
    data_path_rows = []
    summary_rows = []
    delay_attr = "Incr" if "Incr" in parser_impl.attrs_order else "Delay"
    for meta, launch, capture in results:
        lc, dp, lc_n, dp_n, lc_delay, dp_delay = parser_impl.split_launch_by_common_pin(
            launch, meta.get("startpoint", ""), delay_attr=delay_attr
        )
        meta["launch_clock_point_count"] = lc_n
        meta["data_path_point_count"] = dp_n
        meta["capture_point_count"] = len(capture)
        meta["launch_clock_delay"] = parser_impl._clean_metric_float(lc_delay)
        meta["data_path_delay"] = parser_impl._clean_metric_float(dp_delay)
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


def run_extract(args) -> int:
    """执行 extract 子命令：解析 timing 报告并写出 CSV。args 需有 input_rpt, output_dir, format, jobs。"""
    rpt_path = os.path.abspath(args.input_rpt)
    out_dir = os.path.abspath(args.output_dir)
    if not os.path.isfile(rpt_path):
        print(f"Error: input file not found: {rpt_path}", file=sys.stderr)
        return 1

    format_key = args.format
    if format_key == "auto":
        with open(rpt_path, "r", encoding="utf-8", errors="replace") as f:
            format_key = detect_report_format(f.read())
        print(f"Format: {format_key} (auto-detected)")
    else:
        print(f"Format: {format_key}")

    parser_impl = create_parser(format_key)
    result = parse_with_jobs(parser_impl, rpt_path, jobs=args.jobs)

    launch_csv = os.path.join(out_dir, "launch_path.csv")
    capture_csv = os.path.join(out_dir, "capture_path.csv")
    summary_csv = os.path.join(out_dir, "path_summary.csv")
    launch_clock_csv = os.path.join(out_dir, "launch_clock_path.csv")
    data_path_csv = os.path.join(out_dir, "data_path.csv")

    base_cols = parser_impl.point_base_columns + parser_impl.attrs_order
    launch_cols = parser_impl.point_base_columns + ["path_type"] + parser_impl.attrs_order
    parser_impl.write_csv(launch_csv, result.launch_rows, launch_cols)
    parser_impl.write_csv(capture_csv, result.capture_rows, base_cols)
    parser_impl.write_csv(summary_csv, result.summary_rows, parser_impl.summary_columns)
    parser_impl.write_csv(launch_clock_csv, result.launch_clock_rows, base_cols)
    parser_impl.write_csv(data_path_csv, result.data_path_rows, base_cols)

    print(f"Wrote {len(result.launch_rows)} launch rows -> {launch_csv}")
    print(f"Wrote {len(result.capture_rows)} capture rows -> {capture_csv}")
    print(f"Wrote {len(result.summary_rows)} summary rows -> {summary_csv}")
    print(f"Wrote {len(result.launch_clock_rows)} launch clock rows -> {launch_clock_csv}")
    print(f"Wrote {len(result.data_path_rows)} data path rows -> {data_path_csv}")
    return 0
