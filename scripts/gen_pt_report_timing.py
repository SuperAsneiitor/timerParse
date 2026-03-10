#!/usr/bin/env python3
"""
Generate PrimeTime (PT) report_timing TCL script from parsed launch_path.csv.

Rule:
-rise_through <pin>  <=> trigger_edge == 'r' (rise_edge)
-fall_through <pin>  <=> trigger_edge == 'f' (fall_edge)

For backward compatibility, if trigger_edge is missing, fallback to pin-name based
classification (Q/Z/ZN/ZP -> fall, others -> rise).
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from collections import defaultdict


# Pin names that are outputs (use -fall_through); all others treated as inputs (use -rise_through)
OUTPUT_PINS = frozenset({"Q", "Z", "ZN", "ZP"})


def _is_net_or_virtual(point: str) -> bool:
    """Skip nets, clock virtuals, and summary lines."""
    if not point or not point.strip():
        return True
    s = point.strip()
    if s.startswith("clock ") or s == "data arrival time" or s == "pll_cpu_clk":
        return True
    if " (net)" in s or s.endswith("(net)"):
        return True
    return False


def _pin_name_from_point(point: str) -> str | None:
    """Extract pin name from 'inst/pin (CELLTYPE)' -> pin; return None if not a cell pin."""
    # Match last /PIN before space and " ("
    m = re.search(r"/([A-Za-z0-9_\[\]]+)\s*\([A-Z]", point)
    return m.group(1) if m else None


def _is_output_pin(pin_name: str) -> bool:
    """Return True if pin is typically an output (Q, Z, ZN, etc.)."""
    return pin_name in OUTPUT_PINS


def _classify_point(point: str, trigger_edge: str = "") -> str | None:
    """Classify point into rise/fall by trigger_edge first, then fallback to pin-name heuristic."""
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
    """Load launch_path.csv and group rows by path_id, preserving point order. Returns (by_path, metric_columns)."""
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


def _strip_cell_type(point: str) -> str:
    """Remove trailing ' (CELLTYPE)' so PT gets instance/pin only, e.g. inst/U2/A2."""
    if " (" in point and ")" in point:
        return point[: point.rfind(" (")].strip()
    return point.strip()


def build_through_args(points: list[dict], startpoint: str) -> list[tuple[str, str]]:
    """Build list of (option, pin) for -rise_through / -fall_through from startpoint onward."""
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
) -> str:
    """Format one report_timing command. -from/-to use [get_clock clock_name] when clock given, else {pin}. extra_args inserted before -rise_through/-fall_through."""
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
        return f"# path_id {path_id}\n{head}\n"
    if wrap:
        lines = [f"# path_id {path_id}", head + " \\"]
        for opt, pin in through_list:
            lines.append(f"  {opt} {{{pin}}} \\")
        lines[-1] = lines[-1].rstrip(" \\")
        return "\n".join(lines) + "\n"
    parts = [head]
    for opt, pin in through_list:
        parts.append(opt)
        parts.append("{" + pin + "}")
    return f"# path_id {path_id}\n" + " ".join(parts) + "\n"


def main() -> int:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir) if os.path.basename(script_dir) == "scripts" else script_dir
    default_csv = os.path.join(project_root, "output", "launch_path.csv")
    default_out = os.path.join(project_root, "output", "report_timing.tcl")

    parser = argparse.ArgumentParser(
        description="Generate PrimeTime report_timing TCL from launch_path.csv (launch path)."
    )
    parser.add_argument(
        "launch_csv",
        nargs="?",
        default=default_csv,
        help="Path to launch_path.csv",
    )
    parser.add_argument(
        "-o", "--output",
        default=default_out,
        help="Output TCL script path",
    )
    parser.add_argument(
        "-n", "--max-paths",
        type=int,
        default=0,
        metavar="N",
        help="Limit to first N paths (0 = all)",
    )
    parser.add_argument(
        "--no-wrap",
        action="store_true",
        help="Output one long line per report_timing (no backslash continuation)",
    )
    parser.add_argument(
        "--extra",
        default="",
        metavar="ARGS",
        help="Extra report_timing arguments (e.g. '-max_paths 1 -delay_type max'). Inserted after -from/-to, before -rise_through/-fall_through.",
    )
    args = parser.parse_args()

    csv_path = os.path.abspath(args.launch_csv)
    if not os.path.isfile(csv_path):
        print(f"Error: launch_path CSV not found: {csv_path}", file=sys.stderr)
        return 1

    paths, metric_columns = load_launch_paths(csv_path)
    if metric_columns:
        print(f"CSV 指标列: {', '.join(metric_columns)}")
    path_ids = sorted(paths.keys())
    if args.max_paths > 0:
        path_ids = path_ids[: args.max_paths]

    lines = [
        "# PrimeTime report_timing script generated from launch_path.csv",
        "# -from / -to: [get_clocks clock]",
        "# -rise_through / -fall_through are driven by trigger_edge (r/f) when available",
        "",
    ]
    for pid in path_ids:
        rows = paths[pid]
        if not rows:
            continue
        start = rows[0]["startpoint"]
        startpoint_clock = rows[0].get("startpoint_clock", "").strip()
        endpoint_clock = rows[0].get("endpoint_clock", "").strip()
        through_list = build_through_args(rows, start)
        lines.append(format_report_timing(
            pid,
            startpoint_clock,
            endpoint_clock,
            through_list,
            extra_args=args.extra,
            wrap=not args.no_wrap,
            startpoint_pin=start,
            endpoint_pin=rows[0].get("endpoint", ""),
        ))

    out_path = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Wrote {len(path_ids)} report_timing commands -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
