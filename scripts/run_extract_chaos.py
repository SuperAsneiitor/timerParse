#!/usr/bin/env python3
"""
使用 parser_chaos 流水线解析 Timing 报告并输出 CSV。

用法：
  python scripts/run_extract_chaos.py <report.rpt> -o <output_dir> [--format auto|format1|format2|pt] [-j N]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 将项目根加入 path 以便 -m 或直接运行脚本时能导入 lib
_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from lib.parser_chaos import runExtractChaos


def main() -> int:
    # 尽量保证 Windows 下中文输出不乱码
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    parser = argparse.ArgumentParser(
        description="parser_chaos：1 个分割器 + N 个解析器进程，队列式解析 Timing 报告并输出 CSV。"
    )
    parser.add_argument("input_rpt", help="输入 timing 报告文件路径")
    parser.add_argument("-o", "--output-dir", default="output_parser_chaos", help="输出目录（默认：output_parser_chaos）")
    parser.add_argument(
        "-f",
        "--format",
        choices=["auto", "format1", "format2", "pt", "apr"],
        default="auto",
        help="报告格式（默认：auto 自动识别）",
    )
    parser.add_argument("-j", "--jobs", type=int, default=3, metavar="N", help="解析器 Worker 进程数，默认 3")
    parser.add_argument(
        "-l",
        "--log-level",
        choices=["brief", "full"],
        default="brief",
        help="日志等级：brief=每步一行汇总；full=多行展开（默认：brief）",
    )
    args = parser.parse_args()
    return runExtractChaos(
        report_path=args.input_rpt,
        output_dir=args.output_dir,
        format_key=args.format,
        num_workers=args.jobs,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    # 多进程在 Windows 上需要入口保护，避免子进程重复执行
    sys.exit(main())
