from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path


REQUIRED_FILES = {
    "launch_path.csv",
    "capture_path.csv",
    "launch_clock_path.csv",
    "data_path.csv",
    "path_summary.csv",
}


FORMAT_REQUIRED_COLUMNS = {
    "format1": {
        "path_id",
        "point",
        "Cap",
        "Trans",
        "Incr",
        "Path",
        "trigger_edge",
    },
    "format2": {
        "path_id",
        "point",
        "Fanout",
        "Cap",
        "Trans",
        "Derate",
        "x-coord",
        "y-coord",
        "Delay",
        "Time",
        "Description",
    },
    "pt": {
        "path_id",
        "point",
        "Fanout",
        "Cap",
        "Trans",
        "Derate",
        "Mean",
        "Sensit",
        "Incr",
        "Path",
        "trigger_edge",
    },
}


def _readCsv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        return reader.fieldnames or [], rows


def _isLikelyPinPoint(point: str) -> bool:
    p = (point or "").strip().lower()
    if not p:
        return False
    if "(net)" in p:
        return False
    if p.startswith("clock "):
        return False
    if "data arrival time" in p or "data required time" in p:
        return False
    if "slack" in p or "path check period" in p:
        return False
    return "/" in p


def _requiresTriggerEdge(point: str) -> bool:
    """仅对明确应带边沿信息的 pin 行强制检查 trigger_edge。"""
    p = (point or "").strip()
    if not _isLikelyPinPoint(p):
        return False
    lower = p.lower()
    if "<-" in p:
        return True
    # 层级名末级 pin 为输出类时，通常应带 r/f
    leaf = p.split("/")[-1].split()[0].upper() if "/" in p else ""
    return leaf in {"Q", "Z", "ZN", "ZP", "QN", "QB"}


def _validateTriggerEdge(rows: list[dict[str, str]], csv_path: Path) -> list[str]:
    issues: list[str] = []
    pin_rows = [r for r in rows if _requiresTriggerEdge(r.get("point", ""))]
    missing = [r for r in pin_rows if (r.get("trigger_edge") or "").strip().lower() not in {"r", "f"}]
    if missing:
        issues.append(
            f"{csv_path}: {len(missing)}/{len(pin_rows)} 行 pin 的 trigger_edge 为空或非法"
        )
    return issues


def _validateFormat2NetCap(rows: list[dict[str, str]], csv_path: Path) -> list[str]:
    issues: list[str] = []
    net_rows = [r for r in rows if (r.get("Type") or "").strip().lower() == "net"]
    bad_rows = []
    for r in net_rows:
        fanout = (r.get("Fanout") or "").strip()
        cap = (r.get("Cap") or "").strip()
        if fanout and not re.fullmatch(r"-?\d+", fanout):
            bad_rows.append("Fanout")
            break
        if cap and not re.fullmatch(r"-?\d+(?:\.\d+)?", cap):
            bad_rows.append("Cap")
            break
    if bad_rows:
        issues.append(f"{csv_path}: format2 net 行存在非数值 Fanout/Cap（可能解析错位）")
    return issues


def validateOneExtractDir(extract_dir: Path, fmt: str) -> list[str]:
    issues: list[str] = []
    missing_files = [name for name in REQUIRED_FILES if not (extract_dir / name).exists()]
    if missing_files:
        issues.append(f"{extract_dir}: 缺少文件 {missing_files}")
        return issues

    launch_cols, launch_rows = _readCsv(extract_dir / "launch_path.csv")
    capture_cols, capture_rows = _readCsv(extract_dir / "capture_path.csv")
    required_cols = FORMAT_REQUIRED_COLUMNS[fmt]
    launch_missing = sorted(required_cols - set(launch_cols))
    capture_missing = sorted(required_cols - set(capture_cols))
    if launch_missing:
        issues.append(f"{extract_dir}/launch_path.csv: 缺少列 {launch_missing}")
    if capture_missing:
        issues.append(f"{extract_dir}/capture_path.csv: 缺少列 {capture_missing}")

    if fmt in {"format1", "pt"}:
        issues.extend(_validateTriggerEdge(launch_rows, extract_dir / "launch_path.csv"))
        issues.extend(_validateTriggerEdge(capture_rows, extract_dir / "capture_path.csv"))
    if fmt == "format2":
        issues.extend(_validateFormat2NetCap(launch_rows, extract_dir / "launch_path.csv"))
        issues.extend(_validateFormat2NetCap(capture_rows, extract_dir / "capture_path.csv"))
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="校验 extract 结果格式与关键语义字段。")
    parser.add_argument("--validation-base", default="", help="validation_flow_* 目录路径")
    parser.add_argument("--extract-dir", default="", help="单个 extract 目录路径")
    parser.add_argument(
        "--format",
        choices=["format1", "format2", "pt"],
        default="",
        help="当使用 --extract-dir 时指定格式",
    )
    args = parser.parse_args(argv)

    issues: list[str] = []
    checked: list[str] = []

    if args.validation_base:
        base = Path(args.validation_base).resolve()
        for fmt, sub in (("format1", "extract_format1"), ("format2", "extract_format2"), ("pt", "extract_pt")):
            target = base / sub
            checked.append(str(target))
            issues.extend(validateOneExtractDir(target, fmt))

    if args.extract_dir:
        if not args.format:
            print("ERROR: 使用 --extract-dir 时必须提供 --format")
            return 2
        target = Path(args.extract_dir).resolve()
        checked.append(str(target))
        issues.extend(validateOneExtractDir(target, args.format))

    if not checked:
        print("ERROR: 请提供 --validation-base 或 --extract-dir")
        return 2

    print("Checked:")
    for c in checked:
        print(f"  - {c}")

    if issues:
        print("\nValidation FAILED:")
        for item in issues:
            print(f"  - {item}")
        return 1

    print("\nValidation PASSED: 所有检查项符合预期。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
