from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
if str(repo) not in sys.path:
    sys.path.insert(0, str(repo))
from lib import log_util


def run(cmd: list[str], cwd: Path) -> None:
    log_util.full("> " + " ".join(cmd))
    p = subprocess.run(cmd, cwd=str(cwd))
    if p.returncode != 0:
        raise SystemExit(p.returncode)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="固定验证流：生成3格式 -> 解析3格式 -> PT作golden对比format1/format2"
    )
    parser.add_argument("--jobs", type=int, default=4, help="extract 并行 worker 数")
    parser.add_argument("--seed-format1", type=int, default=101)
    parser.add_argument("--seed-format2", type=int, default=202)
    parser.add_argument("--seed-pt", type=int, default=303)
    parser.add_argument(
        "--output-base",
        default="",
        help="可选输出目录；默认 test_results/validation_flow_YYYYMMDD_HHMMSS",
    )
    parser.add_argument(
        "--log-level",
        choices=["brief", "full"],
        default="brief",
        help="日志等级：brief 每步一行汇总，full 多行展开（含子命令回显）",
    )
    args = parser.parse_args(argv)
    log_util.set_level(args.log_level)

    _repo = Path(__file__).resolve().parents[1]
    if args.output_base:
        base = (_repo / args.output_base).resolve()
    else:
        ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        base = _repo / "test_results" / f"validation_flow_{ts}"

    reports = base / "reports"
    ex1 = base / "extract_format1"
    ex2 = base / "extract_format2"
    expt = base / "extract_pt"
    cmpd = base / "compare"
    for d in (reports, ex1, ex2, expt, cmpd):
        d.mkdir(parents=True, exist_ok=True)

    run(
        [
            sys.executable,
            "-m",
            "lib",
            "gen-report",
            "config/gen_report/format1.yaml",
            "--seed",
            str(args.seed_format1),
            "-o",
            str(reports / "gen_format1.rpt"),
            "--log-level",
            args.log_level,
        ],
        _repo,
    )
    run(
        [
            sys.executable,
            "-m",
            "lib",
            "gen-report",
            "config/gen_report/format2.yaml",
            "--seed",
            str(args.seed_format2),
            "-o",
            str(reports / "gen_format2.rpt"),
            "--log-level",
            args.log_level,
        ],
        _repo,
    )
    run(
        [
            sys.executable,
            "-m",
            "lib",
            "gen-report",
            "config/gen_report/pt.yaml",
            "--seed",
            str(args.seed_pt),
            "-o",
            str(reports / "gen_pt.rpt"),
            "--log-level",
            args.log_level,
        ],
        _repo,
    )

    run(
        [
            sys.executable,
            "-m",
            "lib",
            "extract",
            str(reports / "gen_format1.rpt"),
            "--format",
            "format1",
            "-o",
            str(ex1),
            "-j",
            str(args.jobs),
            "--log-level",
            args.log_level,
        ],
        _repo,
    )
    run(
        [
            sys.executable,
            "-m",
            "lib",
            "extract",
            str(reports / "gen_format2.rpt"),
            "--format",
            "format2",
            "-o",
            str(ex2),
            "-j",
            str(args.jobs),
            "--log-level",
            args.log_level,
        ],
        _repo,
    )
    run(
        [
            sys.executable,
            "-m",
            "lib",
            "extract",
            str(reports / "gen_pt.rpt"),
            "--format",
            "pt",
            "-o",
            str(expt),
            "-j",
            str(args.jobs),
            "--log-level",
            args.log_level,
        ],
        _repo,
    )

    run(
        [
            sys.executable,
            "-m",
            "lib",
            "compare",
            str(expt / "path_summary.csv"),
            str(ex1 / "path_summary.csv"),
            "-o",
            str(cmpd / "pt_vs_format1.csv"),
            "--stats-json",
            str(cmpd / "pt_vs_format1_stats.json"),
            "--no-charts",
            "--no-html",
            "--log-level",
            args.log_level,
        ],
        _repo,
    )
    run(
        [
            sys.executable,
            "-m",
            "lib",
            "compare",
            str(expt / "path_summary.csv"),
            str(ex2 / "path_summary.csv"),
            "-o",
            str(cmpd / "pt_vs_format2.csv"),
            "--stats-json",
            str(cmpd / "pt_vs_format2_stats.json"),
            "--no-charts",
            "--no-html",
            "--log-level",
            args.log_level,
        ],
        _repo,
    )

    log_util.brief(f"Validation flow done: {base}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
