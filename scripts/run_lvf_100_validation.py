#!/usr/bin/env python3
"""
生成 100 条 path 的 format1 LVF 合成报告（默认含长 data_path，与 tests/format1_lvf_synth 一致），
执行 extract / extract-chaos（均带 --lvf），并比对五行 CSV 行数；可选调用 validate_extract_results。

用法（仓库根目录）：
  python scripts/run_lvf_100_validation.py
  python scripts/run_lvf_100_validation.py --extra-data-groups 6
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import subprocess
import sys
from pathlib import Path

# 将项目根加入 path
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tests.format1_lvf_synth import DEFAULT_EXTRA_DATA_GROUPS, buildFormat1LvfReport


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
    parser = argparse.ArgumentParser(description="100 path LVF 合成报告 + extract 对齐验证")
    parser.add_argument(
        "-o",
        "--output-base",
        default="",
        help="输出目录；默认 test_results/lvf100_YYYYMMDD_HHMMSS",
    )
    parser.add_argument("-j", "--jobs", type=int, default=4, help="extract / extract-chaos 并行数")
    parser.add_argument(
        "--skip-validate-extract",
        action="store_true",
        help="跳过 scripts/validate_extract_results.py",
    )
    parser.add_argument(
        "--extra-data-groups",
        type=int,
        default=None,
        metavar="N",
        help="合成报告中每条 path 在 Startpoint 后追加的 (input,out,net) 组数，拉长 data_path；默认与 format1_lvf_synth.DEFAULT_EXTRA_DATA_GROUPS 相同",
    )
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    if args.output_base:
        base = (_ROOT / args.output_base).resolve()
    else:
        ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        base = _ROOT / "test_results" / f"lvf100_{ts}"
    reports = base / "reports"
    ex = base / "extract"
    chaos = base / "extract_chaos"
    for d in (reports, ex, chaos):
        d.mkdir(parents=True, exist_ok=True)

    rpt_path = reports / "gen_format1_lvf_100.rpt"
    eg = args.extra_data_groups if args.extra_data_groups is not None else DEFAULT_EXTRA_DATA_GROUPS
    rpt_path.write_text(buildFormat1LvfReport(100, extra_data_groups=eg), encoding="utf-8")
    print(f"Wrote -> {rpt_path}")

    py = sys.executable
    for name, out_dir, sub in (
        ("extract", ex, "extract"),
        ("extract-chaos", chaos, "extract-chaos"),
    ):
        cmd = [
            py,
            "-m",
            "lib",
            sub,
            str(rpt_path),
            "-o",
            str(out_dir),
            "-f",
            "format1",
            "-j",
            str(args.jobs),
            "--lvf",
        ]
        print("> " + " ".join(cmd))
        p = subprocess.run(cmd, cwd=str(_ROOT))
        if p.returncode != 0:
            print(f"ERROR: {name} 失败", file=sys.stderr)
            return p.returncode

    names = [
        "launch_path.csv",
        "capture_path.csv",
        "path_summary.csv",
        "launch_clock_path.csv",
        "data_path.csv",
    ]
    issues = _compare_dirs(ex, chaos, names)
    if issues:
        print("行数不一致:")
        for x in issues:
            print(f"  - {x}")
        return 1
    print("OK: extract 与 extract-chaos 五行 CSV 行数一致。")

    if not args.skip_validate_extract:
        ve = _ROOT / "scripts" / "validate_extract_results.py"
        cmd_v = [py, str(ve), "-d", str(ex), "-f", "format1"]
        print("> " + " ".join(cmd_v))
        p = subprocess.run(cmd_v, cwd=str(_ROOT))
        if p.returncode != 0:
            return p.returncode

    print(f"Done: {base}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
