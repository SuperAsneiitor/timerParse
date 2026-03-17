"""
根据 launch_path.csv 生成 PrimeTime report_timing TCL。

规则：trigger_edge=='r' -> -rise_through，'f' -> -fall_through；
无 trigger_edge 时按 pin 名回退（Q/Z/ZN/ZP -> fall，其余 -> rise）。
"""
from __future__ import annotations

import csv
import os
import re
import sys
from collections import defaultdict
from multiprocessing import Pool, cpu_count
from pathlib import Path
from typing import List

from . import log_util

OUTPUT_PINS = frozenset({"Q", "Z", "ZN", "ZP"})


def _is_net_or_virtual(point: str) -> bool:
    if not point or not point.strip():
        return True
    s = point.strip()
    if s.startswith("clock ") or s == "data arrival time" or s == "pll_cpu_clk":
        return True
    if " (net)" in s or s.endswith("(net)"):
        return True
    return False


def _pin_name_from_point(point: str) -> str | None:
    m = re.search(r"/([A-Za-z0-9_\[\]]+)\s*\([A-Z]", point)
    return m.group(1) if m else None


def _is_output_pin(pin_name: str) -> bool:
    return pin_name in OUTPUT_PINS


def _classify_point(point: str, trigger_edge: str = "") -> str | None:
    if _is_net_or_virtual(point):
        return None
    edge = (trigger_edge or "").strip().lower()
    if edge == "r":
        return "rise"
    if edge == "f":
        return "fall"
    pin = _pin_name_from_point(point)
    if pin is None:
        return None
    return "fall" if _is_output_pin(pin) else "rise"


def load_launch_paths(csv_path: str) -> tuple[dict[int, list[dict]], list[str]]:
    FIXED_COLUMNS = frozenset({
        "path_id", "startpoint", "endpoint", "startpoint_clock", "endpoint_clock",
        "slack", "slack_status", "point_index", "point",
    })
    by_path: dict[int, list[dict]] = defaultdict(list)
    metric_columns: list[str] = []
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames:
            metric_columns = [c for c in reader.fieldnames if c not in FIXED_COLUMNS]
        for row in reader:
            pid = int(row["path_id"])
            by_path[pid].append(row)
    for pid in by_path:
        by_path[pid].sort(key=lambda r: int(r["point_index"]))
    return dict(by_path), metric_columns


def iterLaunchPathsFromCsv(csv_path: str):
    """按 path_id 分组迭代读取单个 launch_path CSV，返回 (path_id, rows, metric_columns)。"""
    FIXED_COLUMNS = frozenset({
        "path_id", "startpoint", "endpoint", "startpoint_clock", "endpoint_clock",
        "slack", "slack_status", "point_index", "point",
    })
    metric_columns: list[str] = []
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames:
            metric_columns = [c for c in reader.fieldnames if c not in FIXED_COLUMNS]
        current_pid: int | None = None
        current_rows: list[dict] = []
        for row in reader:
            pid = int(row["path_id"])
            if current_pid is None:
                current_pid = pid
            if pid != current_pid:
                current_rows.sort(key=lambda r: int(r.get("point_index") or 0))
                yield current_pid, current_rows, metric_columns
                current_pid = pid
                current_rows = []
            current_rows.append(row)
        if current_pid is not None:
            current_rows.sort(key=lambda r: int(r.get("point_index") or 0))
            yield current_pid, current_rows, metric_columns


def _strip_cell_type(point: str) -> str:
    if " (" in point and ")" in point:
        return point[: point.rfind(" (")].strip()
    return point.strip()


def build_through_args(points: list[dict], startpoint: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    found_start = False
    for row in points:
        point = row.get("point", "").strip()
        pin_ref = _strip_cell_type(point)
        if not found_start:
            if pin_ref == startpoint:
                found_start = True
            else:
                continue
        kind = _classify_point(point, str(row.get("trigger_edge", "")))
        if kind is None:
            continue
        if kind == "rise":
            out.append(("-rise_through", pin_ref))
        else:
            out.append(("-fall_through", pin_ref))
    return out


def format_report_timing(
    path_id: int,
    startpoint_clock: str,
    endpoint_clock: str,
    through_list: list[tuple[str, str]],
    extra_args: str = "",
    wrap: bool = True,
    startpoint_pin: str = "",
    endpoint_pin: str = "",
    output_var_expr: str = "${output_file}",
) -> str:
    if startpoint_clock:
        from_arg = f"[get_clocks {startpoint_clock}]"
    elif startpoint_pin:
        from_arg = f"{{{startpoint_pin}}}"
    else:
        from_arg = "{}"
    if endpoint_clock:
        to_arg = f"[get_clocks {endpoint_clock}]"
    elif endpoint_pin:
        to_arg = f"{{{endpoint_pin}}}"
    else:
        to_arg = "{}"
    head = f"report_timing -from {from_arg} -to {to_arg}"
    if extra_args:
        head += " " + extra_args.strip()
    if not through_list:
        return f"# path_id {path_id}\n{head} >> {output_var_expr}\n"
    if wrap:
        lines = [f"# path_id {path_id}", head + " \\"]
        for opt, pin in through_list:
            lines.append(f"  {opt} {{{pin}}} \\")
        lines[-1] = lines[-1].rstrip(" \\") + f" >> {output_var_expr}"
        return "\n".join(lines) + "\n"
    parts = [head]
    for opt, pin in through_list:
        parts.append(opt)
        parts.append("{" + pin + "}")
    return f"# path_id {path_id}\n" + " ".join(parts) + f" >> {output_var_expr}\n"


def _worker_build_command(
    args: tuple[int, list[dict], str, bool, str],
) -> str:
    path_id, rows, extra_args, wrap, report_file = args
    if not rows:
        return ""
    start = rows[0]["startpoint"]
    startpoint_clock = rows[0].get("startpoint_clock", "").strip()
    endpoint_clock = rows[0].get("endpoint_clock", "").strip()
    through_list = build_through_args(rows, start)
    return format_report_timing(
        path_id,
        startpoint_clock,
        endpoint_clock,
        through_list,
        extra_args=extra_args,
        wrap=wrap,
        startpoint_pin=start,
        endpoint_pin=rows[0].get("endpoint", ""),
        output_var_expr="${output_file}",
    )


def run_gen_pt(args) -> int:
    """执行 gen-pt 子命令。args 需有 launch_csv, output, max_paths, no_wrap, extra, report_file, jobs。"""
    launch_glob = (getattr(args, "launch_glob", "") or "").strip()
    launch_csv = (getattr(args, "launch_csv", "") or "").strip()
    csv_inputs: list[str] = []
    if launch_glob:
        csv_inputs = [str(p) for p in sorted(Path().glob(launch_glob))]
    else:
        # 兼容：位置参数若包含通配符，也按 glob 处理
        if any(ch in launch_csv for ch in ["*", "?", "["]):
            csv_inputs = [str(p) for p in sorted(Path().glob(launch_csv))]
        else:
            csv_inputs = [os.path.abspath(launch_csv)]

    csv_inputs = [os.path.abspath(p) for p in csv_inputs if p]
    if not csv_inputs:
        log_util.error("Error: 未找到任何 launch_path CSV 输入。")
        log_util.error("  用法1：python -m lib gen-pt path/to/launch_path.csv")
        log_util.error("  用法2：python -m lib gen-pt -g \"out/launch_path_part*.csv\"")
        return 1
    for p in csv_inputs:
        if not os.path.isfile(p):
            log_util.error(f"Error: launch_path CSV not found: {p}")
            return 1

    out_path = os.path.abspath(getattr(args, "output", "output/report_timing.tcl"))
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    max_paths = int(getattr(args, "max_paths", 0) or 0)
    wrap = not getattr(args, "no_wrap", False)
    extra_args = getattr(args, "extra", "")

    written = 0
    metric_columns: list[str] = []
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# PrimeTime report_timing script generated from launch_path.csv\n")
        f.write("# -from / -to: [get_clocks clock]\n")
        f.write("# -rise_through / -fall_through are driven by trigger_edge (r/f) when available\n")
        f.write(f"set output_file \"{args.report_file}\"\n")
        f.write("sh rm -rf ${output_file}\n")
        f.write("sh touch ${output_file}\n\n")

        for csv_path in csv_inputs:
            for pid, rows, cols in iterLaunchPathsFromCsv(csv_path):
                if cols and not metric_columns:
                    metric_columns = cols
                if not rows:
                    continue
                if max_paths > 0 and written >= max_paths:
                    break
                start = rows[0].get("startpoint", "")
                startpoint_clock = rows[0].get("startpoint_clock", "").strip()
                endpoint_clock = rows[0].get("endpoint_clock", "").strip()
                through_list = build_through_args(rows, start)
                f.write(
                    format_report_timing(
                        pid,
                        startpoint_clock,
                        endpoint_clock,
                        through_list,
                        extra_args=extra_args,
                        wrap=wrap,
                        startpoint_pin=start,
                        endpoint_pin=rows[0].get("endpoint", ""),
                        output_var_expr="${output_file}",
                    )
                )
                written += 1
            if max_paths > 0 and written >= max_paths:
                break

    if metric_columns:
        log_util.full(f"CSV 指标列: {', '.join(metric_columns)}")
    log_util.brief(f"Wrote {written} report_timing commands -> {out_path}")
    if len(csv_inputs) > 1:
        log_util.full(f"Inputs: {len(csv_inputs)} files")
    return 0
