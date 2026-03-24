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
    # 尽量保证 Windows 下中文输出不乱码
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    parser = argparse.ArgumentParser(
        description="固定验证流：生成3格式 -> 解析3格式 -> PT作golden对比format1/format2"
    )
    parser.add_argument("-j", "--jobs", type=int, default=4, help="extract 并行 worker 数（默认：4）")
    parser.add_argument("--seed-format1", type=int, default=101, help="format1 生成随机种子（默认：101）")
    parser.add_argument("--seed-format2", type=int, default=202, help="format2 生成随机种子（默认：202）")
    parser.add_argument("--seed-pt", type=int, default=303, help="pt 生成随机种子（默认：303）")
    parser.add_argument(
        "-o",
        "--output-base",
        default="",
        help="可选输出目录；默认 test_results/validation_flow_YYYYMMDD_HHMMSS",
    )
    parser.add_argument(
        "-l",
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

    _gen_pt_common = [
        "--extra",
        "-delay_type max -path_type full_clock",
        "--log-level",
        args.log_level,
    ]

    # 额外验证：三份 launch_path 均跑 gen-pt（format1/format2 默认 exact，PT 用 instance）
    run(
        [
            sys.executable,
            "-m",
            "lib",
            "gen-pt",
            str(ex1 / "launch_path.csv"),
            "-o",
            str(reports / "report_timing_format1.tcl"),
            "--output-file",
            str(reports / "format1_report_paths.rpt"),
            "--startpoint-match",
            "exact",
            *_gen_pt_common,
        ],
        _repo,
    )
    run(
        [
            sys.executable,
            "-m",
            "lib",
            "gen-pt",
            str(ex2 / "launch_path.csv"),
            "-o",
            str(reports / "report_timing_format2.tcl"),
            "--output-file",
            str(reports / "format2_report_paths.rpt"),
            "--startpoint-match",
            "exact",
            *_gen_pt_common,
        ],
        _repo,
    )
    run(
        [
            sys.executable,
            "-m",
            "lib",
            "gen-pt",
            str(expt / "launch_path.csv"),
            "-o",
            str(reports / "report_timing_pt.tcl"),
            "--output-file",
            str(reports / "pt_report_paths.rpt"),
            "--startpoint-match",
            "instance",
            *_gen_pt_common,
        ],
        _repo,
    )

    run(
        [
            sys.executable,
            "-m",
            "lib",
            "compare",
            "-g",
            str(expt / "path_summary.csv"),
            "-t",
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
            "-g",
            str(expt / "path_summary.csv"),
            "-t",
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

    detail = cmpd / "detail_pt_vs_format1"
    detail.mkdir(parents=True, exist_ok=True)
    run(
        [
            sys.executable,
            "-m",
            "lib",
            "compare",
            "-g",
            str(expt / "path_summary.csv"),
            "-t",
            str(ex1 / "path_summary.csv"),
            "-o",
            str(detail / "compare.csv"),
            "--stats-json",
            str(detail / "compare_stats.json"),
            "--golden-launch-csv",
            str(expt / "launch_path.csv"),
            "--test-launch-csv",
            str(ex1 / "launch_path.csv"),
            "--golden-capture-csv",
            str(expt / "capture_path.csv"),
            "--test-capture-csv",
            str(ex1 / "capture_path.csv"),
            "--no-charts",
            "--log-level",
            args.log_level,
        ],
        _repo,
    )

    log_util.brief(f"Validation flow done: {base}")
    log_util.brief(
        "Generated gen-pt TCL -> "
        f"{reports / 'report_timing_format1.tcl'}, "
        f"{reports / 'report_timing_format2.tcl'}, "
        f"{reports / 'report_timing_pt.tcl'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
