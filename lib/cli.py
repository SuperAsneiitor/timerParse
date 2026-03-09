from __future__ import annotations

import argparse
import os
import sys

from . import create_parser, detect_report_format


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
    result = parser_impl.parse_report(rpt_path)

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
