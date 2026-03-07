#!/usr/bin/env python3
"""
Parse APR Timing report (place_REG2REG.rpt): extract per-path Startpoint, Endpoint,
launch path / capture path points with Fanout, Cap, Trans; output launch_path.csv and capture_path.csv.
Supports multi-process parsing via --jobs N for large files.
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from multiprocessing import Pool, cpu_count
from typing import Any


# ---------------------------------------------------------------------------
# Report structure
# ---------------------------------------------------------------------------
RE_STARTPOINT = re.compile(r"^\s+Startpoint:\s+(.+?)\s+\(.+\)\s*$")
RE_ENDPOINT = re.compile(r"^\s+Endpoint:\s+(.+?)\s+\(.+\)\s*$")
RE_CLOCKED_BY = re.compile(r"clocked by (\w+)")
RE_SLACK = re.compile(r"^\s+slack\s+\((VIOLATED|MET)\)\s")
RE_SLACK_VALUE = re.compile(r"(-?\d+\.\d+)\s*$")
RE_POINT_HEADER = re.compile(r"^\s+Point\s+", re.IGNORECASE)
RE_SEP_LINE = re.compile(r"^\s+-{3,}\s*$")
RE_CLOCK_RISE = re.compile(r"^\s+clock\s+CPU_CLK\s+\(rise\s+edge\)\s")
RE_DATA_ARRIVAL = re.compile(r"^\s+data\s+arrival\s+time\s")
RE_LIBRARY_SETUP = re.compile(r"^\s+library\s+setup\s+time\s")


# 可配置的 Point 表指标列名，与报告表头一致；后续可扩展新指标
DEFAULT_POINT_METRICS = ["Fanout", "Cap", "Trans"]


def _column_positions(header_line: str, metric_names: list[str]) -> dict[str, int]:
    """Find start index of each configured metric and Location in the Point table header."""
    out: dict[str, int] = {}
    for name in metric_names + ["Location"]:
        idx = header_line.find(" " + name + " ")
        if idx >= 0:
            out[name] = idx
        else:
            idx = header_line.find(name)
            if idx >= 0:
                out[name] = idx
    return out


def _parse_point_line(line: str, col_pos: dict[str, int], metric_names: list[str]) -> dict[str, Any]:
    """Parse one Point table line into point name and each configured metric."""
    s = line.rstrip()
    if not s.strip():
        return {}
    if col_pos and metric_names:
        # 按列起始位置排序，得到 [..., Location]
        ordered = sorted(
            [n for n in metric_names + ["Location"] if n in col_pos],
            key=lambda n: col_pos[n],
        )
        if not ordered:
            return {}
        first_start = col_pos[ordered[0]]
        point = s[:first_start].strip() if first_start else s.strip()
        result: dict[str, Any] = {"point": point}
        for i, name in enumerate(ordered):
            start = col_pos[name]
            end = col_pos[ordered[i + 1]] if i + 1 < len(ordered) else len(s)
            val = s[start:end].strip() if start < end else ""
            if name == "Location":
                continue
            if val == "-":
                val = ""
            result[name] = val
        for m in metric_names:
            if m not in result:
                result[m] = ""
        return result
    # Fallback: net line with only fanout at end
    fm = re.search(r"(\d+)\s*$", s)
    if fm:
        return {"point": s[: fm.start()].strip(), **{m: (fm.group(1) if m == "Fanout" else "") for m in metric_names}}
    return {"point": s.strip(), **{m: "" for m in metric_names}}


def parse_one_path(path_id: int, path_text: str, metric_names: list[str]) -> tuple[dict[str, Any], list[dict], list[dict]]:
    """
    Parse a single timing path block. Returns (meta, launch_rows, capture_rows).
    meta: {startpoint, endpoint, slack, slack_status}
    launch_rows / capture_rows: list of {path_id, startpoint, endpoint, ..., point_index, point, <metrics>}
    """
    lines = path_text.splitlines()
    meta: dict[str, Any] = {
        "path_id": path_id,
        "startpoint": "",
        "endpoint": "",
        "startpoint_clock": "",
        "endpoint_clock": "",
        "slack": "",
        "slack_status": "",
    }
    launch_rows: list[dict[str, Any]] = []
    capture_rows: list[dict[str, Any]] = []

    for line in lines:
        m = RE_STARTPOINT.match(line)
        if m:
            meta["startpoint"] = m.group(1).strip()
            cm = RE_CLOCKED_BY.search(line)
            meta["startpoint_clock"] = cm.group(1).strip() if cm else ""
            continue
        m = RE_ENDPOINT.match(line)
        if m:
            meta["endpoint"] = m.group(1).strip()
            cm = RE_CLOCKED_BY.search(line)
            meta["endpoint_clock"] = cm.group(1).strip() if cm else ""
            continue
        m = RE_SLACK.match(line)
        if m:
            meta["slack_status"] = m.group(1).strip()
            vm = RE_SLACK_VALUE.search(line)
            meta["slack"] = vm.group(1).strip() if vm else ""
            break

    # Find Point table header and separator (first occurrence in block)
    col_pos: dict[str, int] = {}
    table_start = 0
    for idx in range(len(lines)):
        if RE_POINT_HEADER.match(lines[idx]):
            header_line = lines[idx]
            col_pos = _column_positions(header_line, metric_names)
            # 至少需要 Location 与一个指标列才认为是有效表头
            if "Location" in col_pos and any(m in col_pos for m in metric_names):
                table_start = idx + 1
                if table_start < len(lines) and RE_SEP_LINE.match(lines[table_start]):
                    table_start += 1
                break
            col_pos = {}

    # Launch path: from first "clock CPU_CLK (rise edge)" to "data arrival time" (inclusive)
    in_launch = False
    launch_start_idx = -1
    for j in range(table_start, len(lines)):
        if RE_CLOCK_RISE.match(lines[j]):
            in_launch = True
            launch_start_idx = j
            continue
        if in_launch and RE_DATA_ARRIVAL.match(lines[j]):
            for k in range(launch_start_idx, j + 1):
                row = _parse_point_line(lines[k], col_pos, metric_names)
                if row and row.get("point"):
                    launch_rows.append({
                        "path_id": path_id,
                        "startpoint": meta["startpoint"],
                        "endpoint": meta["endpoint"],
                        "startpoint_clock": meta["startpoint_clock"],
                        "endpoint_clock": meta["endpoint_clock"],
                        "slack": meta["slack"],
                        "slack_status": meta["slack_status"],
                        "point_index": len(launch_rows) + 1,
                        "point": row["point"],
                        **{m: row.get(m, "") for m in metric_names},
                    })
            break

    # Capture path: after "data arrival time", from next "clock CPU_CLK (rise edge)" to before "library setup time"
    after_data_arrival = False
    in_capture = False
    capture_start_idx = -1
    for j in range(table_start, len(lines)):
        if RE_DATA_ARRIVAL.match(lines[j]):
            after_data_arrival = True
            continue
        if after_data_arrival and RE_CLOCK_RISE.match(lines[j]):
            in_capture = True
            capture_start_idx = j
            continue
        if in_capture and RE_LIBRARY_SETUP.match(lines[j]):
            for k in range(capture_start_idx, j):
                row = _parse_point_line(lines[k], col_pos, metric_names)
                if row and row.get("point"):
                    capture_rows.append({
                        "path_id": path_id,
                        "startpoint": meta["startpoint"],
                        "endpoint": meta["endpoint"],
                        "startpoint_clock": meta["startpoint_clock"],
                        "endpoint_clock": meta["endpoint_clock"],
                        "slack": meta["slack"],
                        "slack_status": meta["slack_status"],
                        "point_index": len(capture_rows) + 1,
                        "point": row["point"],
                        **{m: row.get(m, "") for m in metric_names},
                    })
            break

    return (meta, launch_rows, capture_rows)


def scan_path_blocks(rpt_path: str) -> list[tuple[int, int, int, str]]:
    """
    Single-pass scan: read file and split into path blocks.
    Returns list of (path_id, 0, 0, path_text) for each timing path.
    """
    with open(rpt_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    lines = content.splitlines()
    blocks: list[tuple[int, int, int, str]] = []
    path_id = 0
    i = 0
    while i < len(lines):
        if RE_STARTPOINT.match(lines[i]):
            start_i = i
            path_id += 1
            i += 1
            while i < len(lines):
                if RE_STARTPOINT.match(lines[i]):
                    break
                if RE_SLACK.match(lines[i]):
                    i += 1
                    break
                i += 1
            block_text = "\n".join(lines[start_i:i])
            blocks.append((path_id, 0, 0, block_text))
            continue
        i += 1
    return blocks


def _worker_parse(args: tuple) -> tuple[dict, list, list]:
    """Worker: parse one path block. args = (path_id, path_text, metric_names)."""
    path_id, path_text, metric_names = args
    meta, launch_rows, capture_rows = parse_one_path(path_id, path_text, metric_names)
    return (meta, launch_rows, capture_rows)


def run_single_process(path_blocks: list[tuple[int, int, int, str]], metric_names: list[str]) -> tuple[list[dict], list[dict]]:
    """Parse all blocks in the main process."""
    all_launch: list[dict] = []
    all_capture: list[dict] = []
    for (path_id, _, _, text) in path_blocks:
        _, launch_rows, capture_rows = parse_one_path(path_id, text, metric_names)
        all_launch.extend(launch_rows)
        all_capture.extend(capture_rows)
    return (all_launch, all_capture)


def run_multi_process(path_blocks: list[tuple[int, int, int, str]], jobs: int, metric_names: list[str]) -> tuple[list[dict], list[dict]]:
    """Distribute path blocks across workers."""
    args_list = [(pid, text, metric_names) for (pid, _, _, text) in path_blocks]
    with Pool(processes=jobs) as pool:
        results = pool.map(_worker_parse, args_list)
    all_launch: list[dict] = []
    all_capture: list[dict] = []
    for (_meta, launch_rows, capture_rows) in results:
        all_launch.extend(launch_rows)
        all_capture.extend(capture_rows)
    return (all_launch, all_capture)


def write_csv(out_path: str, rows: list[dict], columns: list[str]) -> None:
    """Write rows to CSV with given column order."""
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir) if os.path.basename(script_dir) == "scripts" else script_dir
    default_input = os.path.join(project_root, "input", "place_REG2REG.rpt")
    default_output = os.path.join(project_root, "output")

    parser = argparse.ArgumentParser(description="Parse APR Timing report to launch_path.csv and capture_path.csv")
    parser.add_argument(
        "input_rpt",
        nargs="?",
        default=default_input,
        help="Path to place_REG2REG.rpt",
    )
    parser.add_argument(
        "-o", "--output-dir",
        default=default_output,
        help="Output directory for CSV files",
    )
    parser.add_argument(
        "-j", "--jobs",
        type=int,
        default=1,
        metavar="N",
        help="Number of parallel workers (default 1). Use >1 for large files.",
    )
    parser.add_argument(
        "--metrics",
        nargs="*",
        default=None,
        metavar="NAME",
        help="Point table metric column names (default: Fanout Cap Trans). Example: --metrics Fanout Cap Trans",
    )
    args = parser.parse_args()

    metric_names = args.metrics if args.metrics is not None else DEFAULT_POINT_METRICS.copy()
    print(f"Point metrics: {', '.join(metric_names)}")

    rpt_path = os.path.abspath(args.input_rpt)
    out_dir = os.path.abspath(args.output_dir)
    if not os.path.isfile(rpt_path):
        print(f"Error: input file not found: {rpt_path}", file=sys.stderr)
        return 1

    print(f"Scanning: {rpt_path}")
    path_blocks = scan_path_blocks(rpt_path)
    # path_blocks from scan: list of (path_id, 0, 0, path_text) — we used 4-tuple for consistency
    if not path_blocks:
        print("No timing paths found.", file=sys.stderr)
        return 0

    n_paths = len(path_blocks)
    print(f"Found {n_paths} timing path(s).")

    jobs = args.jobs
    if jobs <= 0:
        jobs = max(1, cpu_count() - 1)
    if jobs > 1 and n_paths < 100:
        jobs = 1
        print("Using single process (path count < 100).")
    elif jobs > 1:
        print(f"Parsing with {jobs} workers.")

    if jobs <= 1:
        all_launch, all_capture = run_single_process(path_blocks, metric_names)
    else:
        all_launch, all_capture = run_multi_process(path_blocks, jobs, metric_names)

    columns = ["path_id", "startpoint", "endpoint", "startpoint_clock", "endpoint_clock", "slack", "slack_status", "point_index", "point"] + metric_names
    launch_path = os.path.join(out_dir, "launch_path.csv")
    capture_path = os.path.join(out_dir, "capture_path.csv")

    write_csv(launch_path, all_launch, columns)
    write_csv(capture_path, all_capture, columns)

    print(f"Wrote {len(all_launch)} launch path rows -> {launch_path}")
    print(f"Wrote {len(all_capture)} capture path rows -> {capture_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
