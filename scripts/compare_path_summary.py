#!/usr/bin/env python3
"""
对比两个 path_summary CSV 文件（golden vs test）。
按 path_id 对齐，对 arrival_time、required_time、slack 计算 (test - golden) / golden，输出对比结果 CSV。
"""

import argparse
import csv
import sys
from pathlib import Path


def _float(s: str):
    s = (s or "").strip()
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _ratio(test_val: float | None, golden_val: float | None) -> str:
    """(test - golden) / golden，golden 为 0 或空时返回空字符串。"""
    if golden_val is None or test_val is None:
        return ""
    if golden_val == 0:
        return ""
    return f"{(test_val - golden_val) / golden_val:.6f}"


def load_summary(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def compare(golden_rows: list[dict], test_rows: list[dict]) -> list[dict]:
    golden_by_id = {row["path_id"]: row for row in golden_rows if row.get("path_id")}
    test_by_id = {row["path_id"]: row for row in test_rows if row.get("path_id")}
    path_ids = sorted(
        (p for p in golden_by_id if p in test_by_id),
        key=lambda x: (int(x) if str(x).isdigit() else 0, x),
    )
    out = []
    for pid in path_ids:
        g = golden_by_id[pid]
        t = test_by_id[pid]
        ga = _float(g.get("arrival_time"))
        ta = _float(t.get("arrival_time"))
        gr = _float(g.get("required_time"))
        tr = _float(t.get("required_time"))
        gs = _float(g.get("slack"))
        ts = _float(t.get("slack"))
        out.append({
            "path_id": pid,
            "startpoint": g.get("startpoint", ""),
            "endpoint": g.get("endpoint", ""),
            "arrival_time_golden": g.get("arrival_time", ""),
            "arrival_time_test": t.get("arrival_time", ""),
            "arrival_time_ratio": _ratio(ta, ga),
            "required_time_golden": g.get("required_time", ""),
            "required_time_test": t.get("required_time", ""),
            "required_time_ratio": _ratio(tr, gr),
            "slack_golden": g.get("slack", ""),
            "slack_test": t.get("slack", ""),
            "slack_ratio": _ratio(ts, gs),
        })
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description="对比两个 path_summary CSV：按 path_id 对齐，计算 (test - golden) / golden 并输出 CSV。"
    )
    parser.add_argument("golden_file", help="Golden path_summary.csv 路径")
    parser.add_argument("test_file", help="Test path_summary.csv 路径")
    parser.add_argument("-o", "--output", default="", help="输出 CSV 路径，默认 stdout 同目录下 compare_result.csv")
    args = parser.parse_args()

    golden_path = Path(args.golden_file)
    test_path = Path(args.test_file)
    if not golden_path.is_file():
        print(f"Error: golden file not found: {golden_path}", file=sys.stderr)
        return 1
    if not test_path.is_file():
        print(f"Error: test file not found: {test_path}", file=sys.stderr)
        return 1

    golden_rows = load_summary(str(golden_path))
    test_rows = load_summary(str(test_path))
    if not golden_rows:
        print("Error: golden file has no rows.", file=sys.stderr)
        return 1
    if not test_rows:
        print("Error: test file has no rows.", file=sys.stderr)
        return 1

    result = compare(golden_rows, test_rows)
    if not result:
        print("Warning: no common path_id between the two files.", file=sys.stderr)

    out_path = args.output.strip()
    if not out_path:
        out_path = str(golden_path.parent / "compare_result.csv")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames_full = [
        "path_id", "startpoint", "endpoint",
        "arrival_time_golden", "arrival_time_test", "arrival_time_ratio",
        "required_time_golden", "required_time_test", "required_time_ratio",
        "slack_golden", "slack_test", "slack_ratio",
    ]
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames_full, extrasaction="ignore")
        w.writeheader()
        w.writerows(result)

    simple_path = out_path.parent / (out_path.stem + "_simple" + out_path.suffix)
    fieldnames_simple = ["path_id", "arrival_time_ratio", "required_time_ratio", "slack_ratio"]
    with open(simple_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames_simple, extrasaction="ignore")
        w.writeheader()
        w.writerows(result)

    print(f"Compared {len(result)} path(s) -> {out_path}")
    print(f"Simplified -> {simple_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
