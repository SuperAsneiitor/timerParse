from __future__ import annotations

import argparse
import sys

from . import extract
from . import compare_path_summary as compare_module
from . import gen_pt_report_timing as gen_pt_module
from . import log_util
from .report_gen import run_gen_report as run_gen_report


def _ensure_subcommand(argv: list[str] | None) -> list[str]:
    """若第一个参数不是子命令名，则插入 extract，兼容旧用法 python -m lib report.rpt -o out。"""
    if not argv:
        return argv or []
    known = ("extract", "gen-pt", "compare", "gen-report")
    if argv[0] in known:
        return argv
    return ["extract"] + argv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Timing 报告解析与后处理：解析报告、生成 PT TCL、对比 path_summary。"
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument(
        "-l",
        "--log-level",
        choices=["brief", "full"],
        default="brief",
        help="日志等级：brief=每步一行汇总；full=多行展开（默认：brief）",
    )

    # extract
    ext = subparsers.add_parser("extract", help="解析 Timing 报告，输出多 CSV", parents=[parent])
    ext.add_argument("input_rpt", help="输入 timing report 文件路径")
    ext.add_argument("-o", "--output-dir", default="output_lib", help="输出目录（默认: output_lib）")
    ext.add_argument(
        "-f",
        "--format",
        choices=["auto", "format1", "format2", "pt", "apr"],
        default="auto",
        help="报告格式，默认 auto 自动识别",
    )
    ext.add_argument(
        "-j", "--jobs", type=int, default=1, metavar="N",
        help="并行 worker 数，默认 1",
    )

    # gen-pt
    gp = subparsers.add_parser("gen-pt", help="根据 launch_path.csv 生成 PrimeTime report_timing TCL", parents=[parent])
    gp.add_argument(
        "launch_csv",
        nargs="?",
        default="output/launch_path.csv",
        help="launch_path.csv 路径",
    )
    gp.add_argument("-o", "--output", default="output/report_timing.tcl", help="输出 TCL 路径")
    gp.add_argument("-n", "--max-paths", type=int, default=0, metavar="N", help="仅生成前 N 条 path（0=全部）")
    gp.add_argument("-w", "--no-wrap", action="store_true", help="每条 report_timing 单行输出（不换行）")
    gp.add_argument("-e", "--extra", default="", metavar="ARGS", help="额外 report_timing 参数（原样拼到命令末尾）")
    gp.add_argument("-r", "--report-file", default="report_file.rpt", metavar="RPT", help="TCL 中输出文件名（report_file）")
    gp.add_argument("-j", "--jobs", type=int, default=1, metavar="N", help="多进程 worker 数")

    # compare
    cp = subparsers.add_parser("compare", help="对比两个 path_summary CSV（golden vs test）", parents=[parent])
    # 兼容旧用法：仍支持位置参数（golden_file test_file），但推荐使用显式参数 -g/-t（help 中可见）
    cp.add_argument("golden_file", nargs="?", default="", help="（兼容）Golden path_summary.csv 路径")
    cp.add_argument("test_file", nargs="?", default="", help="（兼容）Test path_summary.csv 路径")
    cp.add_argument("-g", "--golden-file", dest="golden_file_opt", default="", help="Golden path_summary.csv 路径（推荐）")
    cp.add_argument("-t", "--test-file", dest="test_file_opt", default="", help="Test path_summary.csv 路径（推荐）")
    cp.add_argument("-o", "--output", default="", help="输出对比 CSV 路径（默认输出到 golden 文件同目录）")
    cp.add_argument("-T", "--threshold", type=float, default=10.0, help="阈值统计条件（默认：10%%）")
    cp.add_argument("-b", "--bins", type=int, default=50, help="直方图桶数（默认：50）")
    cp.add_argument("-c", "--charts-dir", default="", help="图表输出目录（默认：<output_dir>/charts）")
    cp.add_argument("-C", "--no-charts", action="store_true", help="禁用图表生成")
    cp.add_argument("-H", "--no-html", action="store_true", help="禁用 HTML 报告生成")
    cp.add_argument("-s", "--stats-json", default="", help="统计 JSON 路径（默认：<output_dir>/compare_stats.json）")
    cp.add_argument("-S", "--stats-csv", default="", help="统计 CSV 路径（可选）")

    # gen-report：根据 YAML 生成 timing 报告
    gr = subparsers.add_parser("gen-report", help="根据 YAML 配置生成 Timing 报告（title + path 表格）", parents=[parent])
    gr.add_argument("config", help="YAML 配置文件路径")
    gr.add_argument("-o", "--output", default=None, help="输出报告文件路径（默认按 format 写到 output/gen_<format>_timing_report.rpt）")
    gr.add_argument("-s", "--seed", type=int, default=None, metavar="N", help="随机种子（可复现）")

    return parser


def run_cli(argv: list[str] | None = None) -> int:
    # Windows/PowerShell 下为了确保中文 help 不乱码，尽量强制 stdout/stderr 为 UTF-8。
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    parser = build_parser()
    raw_argv = argv if argv is not None else sys.argv[1:]
    argv_parsed = _ensure_subcommand(raw_argv)
    args = parser.parse_args(argv_parsed)

    if not getattr(args, "command", None):
        parser.print_help()
        return 0

    log_util.set_level(getattr(args, "log_level", "brief"))

    if args.command == "extract":
        return extract.runExtract(args)
    if args.command == "gen-pt":
        return gen_pt_module.run_gen_pt(args)
    if args.command == "compare":
        return compare_module.run_compare(args)
    if args.command == "gen-report":
        return run_gen_report(args)

    parser.print_help()
    return 0
