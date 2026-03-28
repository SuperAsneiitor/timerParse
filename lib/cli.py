from __future__ import annotations

import argparse
import sys

from . import extract
from . import compare_path_summary as compare_module
from . import gen_pt_report_timing as gen_pt_module
from . import log_util
from .parser_chaos import runExtractChaos as runExtractChaosChaos
from .report_gen import run_gen_report as run_gen_report


def _ensure_subcommand(argv: list[str] | None) -> list[str]:
    """若第一个参数不是子命令名，则插入 extract，兼容旧用法 python -m lib report.rpt -o out。"""
    if not argv:
        return argv or []
    known = ("extract", "extract-chaos", "gen-pt", "compare", "gen-report")
    if argv[0] in known:
        return argv
    return ["extract"] + argv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Timing 报告工具链：extract（parser_V2 解析）→ gen-pt / compare / gen-report。"
        )
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

    # extract：主入口，解析实现统一在 lib.parser_V2
    ext = subparsers.add_parser(
        "extract",
        parents=[parent],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="从 Timing 报告抽取 CSV（parser_V2，供 gen-pt / compare 使用）",
        description=(
            "读取一份 Timing 文本报告，写出与下游工具约定好的 CSV 集合。\n\n"
            "默认输出目录下文件：\n"
            "  launch_path.csv, capture_path.csv, path_summary.csv,\n"
            "  launch_clock_path.csv, data_path.csv\n\n"
            "示例：\n"
            "  python -m lib extract report.rpt -o ./out\n"
            "  python -m lib extract huge.rpt -f format2 -j 8\n"
            "  python -m lib report.rpt -o ./out\n"
            "      （省略子命令时等价于 extract）"
        ),
    )
    ext.add_argument("input_rpt", metavar="REPORT", help="Timing 报告文件路径")
    ext.add_argument(
        "-o",
        "--output-dir",
        default="output_lib",
        metavar="DIR",
        help="CSV 输出目录（默认: output_lib）",
    )
    ext.add_argument(
        "-f",
        "--format",
        choices=["auto", "format1", "format2", "pt", "apr"],
        default="auto",
        metavar="FMT",
        help=(
            "报告版式：auto 按内容猜测；format1 与 apr 为同义（APR 点表）；"
            "format2 为 Path Start / Type 表；pt 为 PrimeTime 风格"
        ),
    )
    ext.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=1,
        metavar="N",
        help="并行解析进程数（path 很多时生效；默认 1 单进程）",
    )
    ext.add_argument(
        "-p",
        "--paths-per-shard",
        type=int,
        default=0,
        metavar="N",
        help="分片：每 N 条 path 写一组 *_partK.csv；0 表示单文件（默认）",
    )
    ext.add_argument(
        "-m",
        "--merge-launch",
        action="store_true",
        help="分片模式下额外合并生成 launch_path.csv",
    )

    # extract-chaos：与 extract 相同解析器（parser_V2），多进程队列吞吐更高
    exC = subparsers.add_parser(
        "extract-chaos",
        help="多进程抽取：1 分割器 + N Worker，解析与 extract 一致（parser_V2）",
        parents=[parent],
    )
    exC.add_argument("input_rpt", help="输入 timing 报告文件路径")
    exC.add_argument("-o", "--output-dir", default="output_parser_chaos", help="输出目录（默认：output_parser_chaos）")
    exC.add_argument(
        "-f",
        "--format",
        choices=["auto", "format1", "format2", "pt", "apr"],
        default="auto",
        help="报告格式（默认：auto 自动识别）",
    )
    exC.add_argument("-j", "--jobs", type=int, default=3, metavar="N", help="解析器 Worker 进程数，默认 3")
    exC.add_argument(
        "-p",
        "--paths-per-shard",
        type=int,
        default=0,
        metavar="N",
        help="按 path 数拆分输出文件：每 N 条 path 生成一组 *_partK.csv（0=不拆分，默认）",
    )
    exC.add_argument(
        "-m",
        "--merge-launch",
        action="store_true",
        help="当启用分片输出时，额外合并生成 launch_path.csv（默认不生成）",
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
    gp.add_argument(
        "--output-file",
        dest="output_file",
        default="",
        metavar="RPT_PATH",
        help="PrimeTime report_timing 的重定向输出文件路径（覆盖 -r/--report-file）",
    )
    gp.add_argument(
        "-rise_cmd",
        default="-rise_through",
        metavar="FLAG",
        help="上升沿通过点的参数名（默认：-rise_through）",
    )
    gp.add_argument(
        "-fall_cmd",
        default="-fall_through",
        metavar="FLAG",
        help="下降沿通过点的参数名（默认：-fall_through）",
    )
    gp.add_argument(
        "-g",
        "--launch-glob",
        default="",
        metavar="GLOB",
        help="可选：使用通配符读取多个 launch_path CSV（例如 out/launch_path_part*.csv）；优先级高于位置参数",
    )
    gp.add_argument(
        "--startpoint-match",
        choices=("exact", "instance"),
        default="exact",
        metavar="MODE",
        help="起点匹配：exact=与 startpoint 列对齐（均去掉 (CELL) 后缀再比，默认）；"
        "instance=再允许 PT 式「实例名 + point 为 instance/pin」",
    )
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
    cp.add_argument(
        "--match-by",
        choices=["path_id", "signature"],
        default="path_id",
        help="对齐方式：path_id（默认，验证流）；signature=起终点+path_type+双时钟",
    )
    cp.add_argument(
        "--golden-launch-csv",
        default="",
        metavar="PATH",
        help="可选：golden 侧 launch_path.csv，用于详情页逐点对比",
    )
    cp.add_argument(
        "--test-launch-csv",
        default="",
        metavar="PATH",
        help="可选：test 侧 launch_path.csv（与 golden-launch 同时指定生效）",
    )
    cp.add_argument(
        "--golden-capture-csv",
        default="",
        metavar="PATH",
        help="可选：golden 侧 capture_path.csv",
    )
    cp.add_argument(
        "--test-capture-csv",
        default="",
        metavar="PATH",
        help="可选：test 侧 capture_path.csv",
    )
    cp.add_argument(
        "--page-size",
        type=int,
        default=100,
        metavar="N",
        help="HTML 路径列表分页大小（默认：100）",
    )
    cp.add_argument(
        "--sort-by",
        default="slack_diff",
        metavar="COL",
        help="HTML 路径列表排序字段（默认：slack_diff；也可用 data_path_delay_diff 等）",
    )
    cp.add_argument(
        "--no-sort-abs",
        dest="sort_abs",
        action="store_false",
        default=True,
        help="关闭绝对值排序（默认按绝对值降序）",
    )
    cp.add_argument(
        "--detail-scope",
        choices=["none", "first_page", "all", "topN"],
        default="first_page",
        help="详情页生成范围：none=不生成；first_page=仅第一页；topN=仅生成前 N 条（控制 runtime）；all=全部（路径多时很慢）",
    )
    cp.add_argument(
        "--detail-top-n",
        type=int,
        default=50,
        metavar="N",
        help="当 --detail-scope=topN 时：生成前 N 条详情页（默认：50）",
    )

    # gen-report：根据 YAML 生成 timing 报告
    gr = subparsers.add_parser("gen-report", help="根据 YAML 配置生成 Timing 报告（title + path 表格）", parents=[parent])
    gr.add_argument("config", help="YAML 配置文件路径")
    gr.add_argument("-o", "--output", default=None, help="输出报告文件路径（默认按 format 写到 output/gen_<format>_timing_report.rpt）")
    gr.add_argument("-s", "--seed", type=int, default=None, metavar="N", help="随机种子（可复现）")
    gr.add_argument("--path-manifest-in", dest="path_manifest_in", default="", help="可选：输入 path manifest（JSON/YAML），按同源点序列生成")
    gr.add_argument("--path-manifest-out", dest="path_manifest_out", default="", help="可选：输出本次生成使用的 path manifest（JSON）")

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
    if args.command == "extract-chaos":
        return runExtractChaosChaos(
            report_path=args.input_rpt,
            output_dir=args.output_dir,
            format_key=args.format,
            num_workers=args.jobs,
            paths_per_shard=getattr(args, "paths_per_shard", 0),
            merge_launch=getattr(args, "merge_launch", False),
            log_level=getattr(args, "log_level", "brief"),
        )
    if args.command == "gen-pt":
        return gen_pt_module.run_gen_pt(args)
    if args.command == "compare":
        return compare_module.run_compare(args)
    if args.command == "gen-report":
        return run_gen_report(args)

    parser.print_help()
    return 0
