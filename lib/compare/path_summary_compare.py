from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List

from .. import log_util
from .stats import compute_stats, write_stats_csv, write_stats_json
from .charts import generate_charts
from .csv_path_points import loadSegmentCsvByPathId
from .html_report import generate_html_report


RATIO_COLUMNS = ["arrival_time_ratio", "required_time_ratio", "slack_diff"]

# slack PASS/FAIL 标准（来自 plan：5ps + 5% 双条件）
SLACK_ABS_PASS_PS = 5.0
SLACK_REL_PASS = 0.05

# 路径级完整对比 CSV 的列（保持旧列在前，新增列追加在后）
FIELDNAMES_FULL = [
    "path_id",
    "path_id_test",
    "startpoint",
    "endpoint",
    "path_type",
    "startpoint_clock",
    "endpoint_clock",
    # 旧版已有列（核心三项）
    "arrival_time_golden",
    "arrival_time_test",
    "arrival_time_ratio",
    "required_time_golden",
    "required_time_test",
    "required_time_ratio",
    "slack_golden",
    "slack_test",
    "slack_ratio",
    # 新增：slack_diff / AT_ref / clock_period 及 PASS/FAIL
    "slack_diff",
    "AT_ref",
    "clock_period",
    "slack_diff_AT_ref_ratio",
    "slack_diff_clock_period_ratio",
    "slack_pass",
    # 新增：launch/data 段延迟
    "launch_clock_delay_golden",
    "launch_clock_delay_test",
    "launch_clock_delay_diff",
    "data_path_delay_golden",
    "data_path_delay_test",
    "data_path_delay_diff",
    # 新增：clock 相关 pessimism/uncertainty
    "clock_reconvergence_pessimism_golden",
    "clock_reconvergence_pessimism_test",
    "clock_reconvergence_pessimism_diff",
    "clock_uncertainty_golden",
    "clock_uncertainty_test",
    "clock_uncertainty_diff",
    # 新增：分段点数（辅助判断结构一致性）
    "launch_clock_point_count_golden",
    "launch_clock_point_count_test",
    "launch_clock_point_count_diff",
    "data_path_point_count_golden",
    "data_path_point_count_test",
    "data_path_point_count_diff",
    "capture_point_count_golden",
    "capture_point_count_test",
    "capture_point_count_diff",
]

FIELDNAMES_SIMPLE = [
    "path_id",
    "startpoint",
    "endpoint",
    "arrival_time_ratio",
    "required_time_ratio",
    "slack_diff",
    # 简化版额外带上两段 delay 差异，便于快速筛选
    "launch_clock_delay_diff",
    "data_path_delay_diff",
]


def _float_or_none(s: str) -> float | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _ratio(test_val: float | None, golden_val: float | None) -> str:
    if golden_val is None or test_val is None:
        return ""
    if golden_val == 0:
        return ""
    return f"{((test_val - golden_val) / golden_val) * 100:.3f}%"


def load_summary(path: str) -> List[Dict[str, str]]:
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _build_compare_row(g: Dict[str, str], t: Dict[str, str]) -> Dict[str, str]:
    """基于 golden/test 的单条 path_summary 行构造一条对比行。"""
    pid = g.get("path_id", "")
    pid_t = t.get("path_id", "")
    row: Dict[str, str] = {
        "path_id": pid,
        "path_id_test": pid_t,
        "startpoint": g.get("startpoint", ""),
        "endpoint": g.get("endpoint", ""),
        "path_type": g.get("path_type", ""),
        "startpoint_clock": g.get("startpoint_clock", ""),
        "endpoint_clock": g.get("endpoint_clock", ""),
    }

    # 路径级核心时间指标
    ga = _float_or_none(g.get("arrival_time"))
    ta = _float_or_none(t.get("arrival_time"))
    gr = _float_or_none(g.get("required_time"))
    tr = _float_or_none(t.get("required_time"))
    gs = _float_or_none(g.get("slack"))
    ts = _float_or_none(t.get("slack"))

    row.update(
        {
            "arrival_time_golden": g.get("arrival_time", ""),
            "arrival_time_test": t.get("arrival_time", ""),
            "arrival_time_ratio": _ratio(ta, ga),
            "required_time_golden": g.get("required_time", ""),
            "required_time_test": t.get("required_time", ""),
            "required_time_ratio": _ratio(tr, gr),
            "slack_golden": g.get("slack", ""),
            "slack_test": t.get("slack", ""),
            "slack_ratio": _ratio(ts, gs),
        }
    )

    # slack PASS/FAIL（基于 golden/common_pin_delay + clock_period）
    slack_pass = ""
    slack_diff = None
    AT_ref = None
    clock_period = None
    slack_diff_AT_ref_ratio = None
    slack_diff_clock_period_ratio = None

    if gs is not None and ts is not None:
        slack_diff = ts - gs
        # 1) abs(slack_diff) < 5ps -> PASS
        if abs(slack_diff) < SLACK_ABS_PASS_PS:
            slack_pass = "PASS"
        else:
            # 2) slack_diff 不在阈值内：仅当 golden_slack > 0 时进入二级检查
            if gs > 0:
                arrival_golden = _float_or_none(g.get("arrival_time"))
                common_pin_delay_golden = _float_or_none(g.get("common_pin_delay"))
                clock_period = _float_or_none(g.get("clock_period"))
                if arrival_golden is not None and common_pin_delay_golden is not None:
                    AT_ref = arrival_golden - common_pin_delay_golden

                if (
                    AT_ref is not None
                    and clock_period is not None
                    and AT_ref != 0
                    and clock_period != 0
                ):
                    slack_diff_AT_ref_ratio = slack_diff / AT_ref
                    slack_diff_clock_period_ratio = slack_diff / clock_period
                    if (
                        abs(slack_diff_AT_ref_ratio) < SLACK_REL_PASS
                        and abs(slack_diff_clock_period_ratio) < SLACK_REL_PASS
                    ):
                        slack_pass = "PASS"
                    else:
                        slack_pass = "FAIL"
                else:
                    slack_pass = "FAIL"
            else:
                slack_pass = "FAIL"

    def _fmt_num(v: float | None, nd: int = 6) -> str:
        if v is None:
            return ""
        return f"{v:.{nd}f}"

    def _fmt_ratio_percent(v: float | None) -> str:
        if v is None:
            return ""
        return f"{v * 100:.3f}%"

    row.update(
        {
            "slack_diff": _fmt_num(slack_diff, 6),
            "AT_ref": _fmt_num(AT_ref, 6),
            "clock_period": _fmt_num(clock_period, 6),
            "slack_diff_AT_ref_ratio": _fmt_ratio_percent(slack_diff_AT_ref_ratio),
            "slack_diff_clock_period_ratio": _fmt_ratio_percent(slack_diff_clock_period_ratio),
            "slack_pass": slack_pass,
        }
    )

    # Launch/data 段 delay
    lcd_g = _float_or_none(g.get("launch_clock_delay"))
    lcd_t = _float_or_none(t.get("launch_clock_delay"))
    dpd_g = _float_or_none(g.get("data_path_delay"))
    dpd_t = _float_or_none(t.get("data_path_delay"))
    row["launch_clock_delay_golden"] = g.get("launch_clock_delay", "")
    row["launch_clock_delay_test"] = t.get("launch_clock_delay", "")
    row["launch_clock_delay_diff"] = (
        "" if lcd_g is None or lcd_t is None else f"{lcd_t - lcd_g:.6f}"
    )
    row["data_path_delay_golden"] = g.get("data_path_delay", "")
    row["data_path_delay_test"] = t.get("data_path_delay", "")
    row["data_path_delay_diff"] = (
        "" if dpd_g is None or dpd_t is None else f"{dpd_t - dpd_g:.6f}"
    )

    # clock reconvergence pessimism / uncertainty
    crp_g = _float_or_none(g.get("clock_reconvergence_pessimism"))
    crp_t = _float_or_none(t.get("clock_reconvergence_pessimism"))
    cu_g = _float_or_none(g.get("clock_uncertainty"))
    cu_t = _float_or_none(t.get("clock_uncertainty"))
    row["clock_reconvergence_pessimism_golden"] = g.get("clock_reconvergence_pessimism", "")
    row["clock_reconvergence_pessimism_test"] = t.get("clock_reconvergence_pessimism", "")
    row["clock_reconvergence_pessimism_diff"] = (
        "" if crp_g is None or crp_t is None else f"{crp_t - crp_g:.6f}"
    )
    row["clock_uncertainty_golden"] = g.get("clock_uncertainty", "")
    row["clock_uncertainty_test"] = t.get("clock_uncertainty", "")
    row["clock_uncertainty_diff"] = (
        "" if cu_g is None or cu_t is None else f"{cu_t - cu_g:.6f}"
    )

    # point_count 差异（帮助判断结构一致性）
    for key in [
        "launch_clock_point_count",
        "data_path_point_count",
        "capture_point_count",
    ]:
        gv = _float_or_none(g.get(key))
        tv = _float_or_none(t.get(key))
        row[f"{key}_golden"] = g.get(key, "")
        row[f"{key}_test"] = t.get(key, "")
        row[f"{key}_diff"] = "" if gv is None or tv is None else f"{tv - gv:.0f}"

    return row


def _matchSignatureKey(r: Dict[str, str]) -> tuple:
    return (
        (r.get("startpoint") or "").strip(),
        (r.get("endpoint") or "").strip(),
        (r.get("path_type") or "").strip(),
        (r.get("startpoint_clock") or "").strip(),
        (r.get("endpoint_clock") or "").strip(),
    )


def compareRowsByPathId(golden_rows: List[Dict[str, str]], test_rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """按 path_id 对齐（验证流 PT vs format1/format2 等场景）。"""
    golden_by_id = {row["path_id"]: row for row in golden_rows if row.get("path_id")}
    test_by_id = {row["path_id"]: row for row in test_rows if row.get("path_id")}
    pids = sorted(
        (p for p in golden_by_id if p in test_by_id),
        key=lambda x: (int(x) if str(x).isdigit() else 0, x),
    )
    return [_build_compare_row(golden_by_id[pid], test_by_id[pid]) for pid in pids]


def compareRowsBySignature(golden_rows: List[Dict[str, str]], test_rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """按 (startpoint, endpoint, path_type, clocks) 对齐（同设计双工具对比）。"""
    golden_by_key: Dict[tuple, Dict[str, str]] = {}
    for row in golden_rows:
        key = _matchSignatureKey(row)
        if not any(key):
            continue
        if key in golden_by_key:
            log_util.full(
                f"[compare] golden 重复 signature key={key}, path_id={row.get('path_id')}, 已忽略"
            )
            continue
        golden_by_key[key] = row

    test_by_key: Dict[tuple, Dict[str, str]] = {}
    for row in test_rows:
        key = _matchSignatureKey(row)
        if not any(key):
            continue
        if key in test_by_key:
            log_util.full(
                f"[compare] test 重复 signature key={key}, path_id={row.get('path_id')}, 已忽略"
            )
            continue
        test_by_key[key] = row

    keys = sorted(k for k in golden_by_key if k in test_by_key)
    return [_build_compare_row(golden_by_key[k], test_by_key[k]) for k in keys]


def compareRows(
    golden_rows: List[Dict[str, str]],
    test_rows: List[Dict[str, str]],
    match_by: str = "path_id",
) -> List[Dict[str, str]]:
    if match_by == "signature":
        return compareRowsBySignature(golden_rows, test_rows)
    return compareRowsByPathId(golden_rows, test_rows)


def run_compare_path_summary(args) -> int:
    """执行 compare 子命令的路径级对比实现。"""
    golden_file = (getattr(args, "golden_file_opt", "") or getattr(args, "golden_file", "") or "").strip()
    test_file = (getattr(args, "test_file_opt", "") or getattr(args, "test_file", "") or "").strip()
    if not golden_file or not test_file:
        log_util.error("Error: compare 需要提供 golden/test 两个输入文件。")
        log_util.error("  推荐：python -m lib compare -g <golden_path_summary.csv> -t <test_path_summary.csv>")
        log_util.error("  兼容：python -m lib compare <golden_path_summary.csv> <test_path_summary.csv>")
        return 2

    golden_path = Path(golden_file)
    test_path = Path(test_file)
    if not golden_path.is_file():
        log_util.error(f"Error: golden file not found: {golden_path}")
        return 1
    if not test_path.is_file():
        log_util.error(f"Error: test file not found: {test_path}")
        return 1

    golden_rows = load_summary(str(golden_path))
    test_rows = load_summary(str(test_path))
    if not golden_rows:
        log_util.error("Error: golden file has no rows.")
        return 1
    if not test_rows:
        log_util.error("Error: test file has no rows.")
        return 1

    match_by = (getattr(args, "match_by", "path_id") or "path_id").strip().lower()
    if match_by not in ("path_id", "signature"):
        log_util.error("Error: --match-by 仅支持 path_id 或 signature。")
        return 2
    result = compareRows(golden_rows, test_rows, match_by=match_by)
    if not result:
        log_util.error(
            "Warning: 无对齐行（path_id：两侧 path_id 交集为空；signature：起终/时钟/类型不一致）。"
        )

    glaunch = (getattr(args, "golden_launch_csv", "") or "").strip()
    tlaunch = (getattr(args, "test_launch_csv", "") or "").strip()
    gcapture = (getattr(args, "golden_capture_csv", "") or "").strip()
    tcapture = (getattr(args, "test_capture_csv", "") or "").strip()
    golden_launch_map: Dict[str, List[dict]] | None = None
    test_launch_map: Dict[str, List[dict]] | None = None
    golden_capture_map: Dict[str, List[dict]] | None = None
    test_capture_map: Dict[str, List[dict]] | None = None
    if glaunch and tlaunch:
        golden_launch_map = loadSegmentCsvByPathId(Path(glaunch))
        test_launch_map = loadSegmentCsvByPathId(Path(tlaunch))
        if not golden_launch_map or not test_launch_map:
            log_util.error("Warning: launch_path CSV 为空或文件不存在，详情页将不展示逐点 launch 对比。")
    if gcapture and tcapture:
        golden_capture_map = loadSegmentCsvByPathId(Path(gcapture))
        test_capture_map = loadSegmentCsvByPathId(Path(tcapture))
        if not golden_capture_map or not test_capture_map:
            log_util.error("Warning: capture_path CSV 为空或文件不存在，详情页将不展示逐点 capture 对比。")

    out_path = (
        Path(args.output.strip())
        if getattr(args, "output", "").strip()
        else golden_path.parent / "compare_result.csv"
    )
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 完整 CSV
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES_FULL, extrasaction="ignore")
        w.writeheader()
        w.writerows(result)

    # 简化 CSV
    simple_path = out_path.parent / (out_path.stem + "_simple" + out_path.suffix)
    with open(simple_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES_SIMPLE, extrasaction="ignore")
        w.writeheader()
        w.writerows(result)

    # 统计 JSON / CSV
    threshold = getattr(args, "threshold", 10.0)
    stats = compute_stats(
        result,
        threshold=threshold,
        golden_file=str(golden_path),
        test_file=str(test_path),
    )
    stats_json_path = (
        Path(args.stats_json)
        if getattr(args, "stats_json", "").strip()
        else (out_path.parent / "compare_stats.json")
    )
    write_stats_json(stats, stats_json_path)

    stats_csv_path = Path(args.stats_csv) if getattr(args, "stats_csv", "").strip() else None
    if stats_csv_path:
        write_stats_csv(stats, Path(stats_csv_path))

    # 图表 & HTML 报告
    charts_dir = Path(args.charts_dir) if getattr(args, "charts_dir", "").strip() else (
        out_path.parent / "charts"
    )
    chart_files: Dict[str, str] = {}
    if not getattr(args, "no_charts", False):
        bins = getattr(args, "bins", 50) or 50
        chart_files = generate_charts(result, charts_dir=charts_dir, bins=bins, ratio_columns=RATIO_COLUMNS)

    html_path = out_path.parent / "compare_report.html"
    if not getattr(args, "no_html", False):
        page_size = int(getattr(args, "page_size", 100) or 100)
        sort_by = (getattr(args, "sort_by", "slack_diff") or "slack_diff").strip()
        sort_abs = bool(getattr(args, "sort_abs", True))
        detail_scope = (getattr(args, "detail_scope", "first_page") or "first_page").strip()
        detail_top_n = int(getattr(args, "detail_top_n", 50) or 0)
        generate_html_report(
            html_path=html_path,
            golden_path=golden_path,
            test_path=test_path,
            compared_count=len(result),
            stats=stats,
            chart_files=chart_files,
            charts_dir=charts_dir,
            rows=result,
            golden_launch_by_path_id=golden_launch_map,
            test_launch_by_path_id=test_launch_map,
            golden_capture_by_path_id=golden_capture_map,
            test_capture_by_path_id=test_capture_map,
            page_size=page_size,
            sort_by=sort_by,
            sort_abs=sort_abs,
            detail_scope=detail_scope,
            detail_top_n=detail_top_n,
        )

    log_util.brief(f"golden_file -> {golden_path}")
    log_util.brief(f"test_file -> {test_path}")
    log_util.brief(f"Compared {len(result)} path(s) -> {out_path}")
    log_util.brief(f"Simplified -> {simple_path}")
    log_util.brief(f"Stats JSON -> {stats_json_path}")
    if stats_csv_path:
        log_util.full(f"Stats CSV -> {stats_csv_path}")
    if not getattr(args, "no_charts", False):
        log_util.full(f"Charts dir -> {charts_dir}")
    if not getattr(args, "no_html", False):
        log_util.full(f"HTML report -> {html_path}")
    return 0

