from __future__ import annotations

import argparse
import os
import sys
from multiprocessing import Pool, cpu_count
from typing import Tuple

from . import create_parser, detect_report_format
from .time_parser_base import ParseOutput, TimeParser


def _worker_parse_one(args: tuple[type[TimeParser], int, str]) -> tuple[dict, list, list]:
    parser_cls, path_id, path_text = args
    parser = parser_cls()
    meta, launch, capture = parser.parse_one_path(path_id, path_text)
    return meta, launch, capture


def _parse_with_jobs(
    parser_impl: TimeParser,
    report_path: str,
    jobs: int,
) -> ParseOutput:
    blocks = parser_impl.scan_path_blocks(report_path)
    if not blocks:
        return ParseOutput([], [], [])

    if jobs <= 0:
        jobs = max(1, cpu_count() - 1)
    if jobs == 1 or len(blocks) < 100:
        return parser_impl.parse_report(report_path)

    parser_cls: type[TimeParser] = parser_impl.__class__  # type: ignore[assignment]
    args_list: list[tuple[type[TimeParser], int, str]] = [
        (parser_cls, path_id, path_text) for (path_id, path_text) in blocks
    ]
    with Pool(processes=jobs) as pool:
        results: list[Tuple[dict, list, list]] = pool.map(_worker_parse_one, args_list)

    launch_rows: list[dict] = []
    capture_rows: list[dict] = []
    summary_rows: list[dict] = []
    for meta, launch, capture in results:
        summary_rows.append(meta)
        launch_rows.extend(launch)
        capture_rows.extend(capture)
    return ParseOutput(launch_rows, capture_rows, summary_rows)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Timing report 解析 CLI（lib 版本）"
    )
    parser.add_argument("input_rpt", help="输入 timing report 文件路径")
    parser.add_argument(
        "-o",
        "--output-dir",
        default="output_lib",
        help="输出目录（默认: output_lib）",
    )
    parser.add_argument(
        "--format",
        choices=["auto", "format1", "format2", "pt", "apr"],
        default="auto",
        help="报告格式，默认 auto 自动识别",
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=1,
        metavar="N",
        help="并行 worker 数，默认 1；path 数较大时可设置为 CPU 核心数以加速解析",
    )
    return parser


def run_cli(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    rpt_path = os.path.abspath(args.input_rpt)
    out_dir = os.path.abspath(args.output_dir)
    if not os.path.isfile(rpt_path):
        print(f"Error: input file not found: {rpt_path}", file=sys.stderr)
        return 1

    format_key = args.format
    if format_key == "auto":
        # 为了避免格式特征不在文件开头导致误判，auto 模式读取整份文本做检测
        with open(rpt_path, "r", encoding="utf-8", errors="replace") as f:
            format_key = detect_report_format(f.read())
        print(f"Format: {format_key} (auto-detected)")
    else:
        print(f"Format: {format_key}")

    parser_impl = create_parser(format_key)
    result = _parse_with_jobs(parser_impl, rpt_path, jobs=args.jobs)

    launch_csv = os.path.join(out_dir, "launch_path.csv")
    capture_csv = os.path.join(out_dir, "capture_path.csv")
    summary_csv = os.path.join(out_dir, "path_summary.csv")

    parser_impl.write_csv(
        launch_csv,
        result.launch_rows,
        parser_impl.point_base_columns + parser_impl.attrs_order,
    )
    parser_impl.write_csv(
        capture_csv,
        result.capture_rows,
        parser_impl.point_base_columns + parser_impl.attrs_order,
    )
    parser_impl.write_csv(
        summary_csv,
        result.summary_rows,
        parser_impl.summary_columns,
    )

    print(f"Wrote {len(result.launch_rows)} launch rows -> {launch_csv}")
    print(f"Wrote {len(result.capture_rows)} capture rows -> {capture_csv}")
    print(f"Wrote {len(result.summary_rows)} summary rows -> {summary_csv}")
    return 0
