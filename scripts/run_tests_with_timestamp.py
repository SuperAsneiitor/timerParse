#!/usr/bin/env python3
"""
将测试结果统一输出到 test_results/，并在路径中加上时间戳。
用法:
  python scripts/run_tests_with_timestamp.py extract  <input.rpt>   -> test_results/extract_<ts>/
  python scripts/run_tests_with_timestamp.py gen-report <config.yaml> -> test_results/gen_report_<ts>/
  python scripts/run_tests_with_timestamp.py compare <golden.csv> <test.csv> -> test_results/compare_<ts>/
"""
from __future__ import annotations

import os
import sys
from datetime import datetime

def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def main() -> int:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)
    os.chdir(root)

    args = sys.argv[1:]
    if not args:
        print("Usage: run_tests_with_timestamp.py <extract|gen-report|compare> [args...]", file=sys.stderr)
        return 1
    cmd = args[0].lower()
    ts = _timestamp()
    out_base = os.path.join(root, "test_results")

    if cmd == "extract":
        if len(args) < 2:
            print("Usage: run_tests_with_timestamp.py extract <input.rpt> [--format auto]", file=sys.stderr)
            return 1
        out_dir = os.path.join(out_base, f"extract_{ts}")
        argv = ["extract", args[1], "-o", out_dir] + args[2:]
    elif cmd == "gen-report":
        if len(args) < 2:
            print("Usage: run_tests_with_timestamp.py gen-report <config.yaml>", file=sys.stderr)
            return 1
        out_dir = os.path.join(out_base, f"gen_report_{ts}")
        os.makedirs(out_dir, exist_ok=True)
        out_rpt = os.path.join(out_dir, "gen_timing_report.rpt")
        argv = ["gen-report", args[1], "-o", out_rpt] + args[2:]
    elif cmd == "compare":
        if len(args) < 3:
            print("Usage: run_tests_with_timestamp.py compare <golden.csv> <test.csv> [-o ...]", file=sys.stderr)
            return 1
        out_dir = os.path.join(out_base, f"compare_{ts}")
        os.makedirs(out_dir, exist_ok=True)
        out_csv = os.path.join(out_dir, "compare_result.csv")
        argv = ["compare", args[1], args[2], "-o", out_csv] + args[3:]
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        return 1

    from lib.cli import run_cli
    return run_cli(argv)

if __name__ == "__main__":
    sys.exit(main())
