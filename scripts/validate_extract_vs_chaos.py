#!/usr/bin/env python3
"""
对同一份 timing 报告分别运行 extract 与 extract-chaos，比对各 CSV 行数是否一致。

用法（仓库根目录）：
  python scripts/validate_extract_vs_chaos.py path/to/report.rpt -f format1 -j 4
"""
from __future__ import annotations

import argparse
import csv
import subprocess
import sys
import tempfile
from pathlib import Path


def _count_rows(csv_path: Path) -> int:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        return max(0, sum(1 for _ in csv.reader(f)) - 1)


def _compare_dirs(a: Path, b: Path, names: list[str]) -> list[str]:
    issues: list[str] = []
    for name in names:
        pa, pb = a / name, b / name
        if not pa.exists():
            issues.append(f"缺少 {a}/{name}")
            continue
        if not pb.exists():
            issues.append(f"缺少 {b}/{name}")
            continue
        ca, cb = _count_rows(pa), _count_rows(pb)
        if ca != cb:
            issues.append(f"{name}: extract={ca} extract-chaos={cb}")
    return issues


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="比对 extract 与 extract-chaos 输出 CSV 行数")
    parser.add_argument("report", help="timing 报告 .rpt 路径")
    parser.add_argument("-f", "--format", default="auto", help="format：auto|format1|format2|pt|apr")
    parser.add_argument("-j", "--jobs", type=int, default=4, help="并行数（两边相同）")
    args = parser.parse_args(argv)

    rpt = Path(args.report).resolve()
    if not rpt.is_file():
        print(f"ERROR: 文件不存在: {rpt}", file=sys.stderr)
        return 2

    names = [
        "launch_path.csv",
        "capture_path.csv",
        "path_summary.csv",
        "launch_clock_path.csv",
        "data_path.csv",
    ]

    with tempfile.TemporaryDirectory(prefix="ext_vs_chaos_") as tmp:
        d1 = Path(tmp) / "extract"
        d2 = Path(tmp) / "chaos"
        d1.mkdir()
        d2.mkdir()
        py = sys.executable
        cmd_e = [
            py,
            "-m",
            "lib",
            "extract",
            str(rpt),
            "-o",
            str(d1),
            "-f",
            args.format,
            "-j",
            str(args.jobs),
        ]
        cmd_c = [
            py,
            "-m",
            "lib",
            "extract-chaos",
            str(rpt),
            "-o",
            str(d2),
            "-f",
            args.format,
            "-j",
            str(args.jobs),
        ]
        r1 = subprocess.run(cmd_e, cwd=str(root))
        r2 = subprocess.run(cmd_c, cwd=str(root))
        if r1.returncode != 0:
            print("ERROR: extract 失败", file=sys.stderr)
            return r1.returncode
        if r2.returncode != 0:
            print("ERROR: extract-chaos 失败", file=sys.stderr)
            return r2.returncode

        issues = _compare_dirs(d1, d2, names)
        if issues:
            print("行数不一致:")
            for x in issues:
                print(f"  - {x}")
            return 1
        print("OK: extract 与 extract-chaos 五行 CSV 行数一致。")
        print(f"  {d1}")
        print(f"  {d2}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
