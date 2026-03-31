from __future__ import annotations

import csv
import json
import math
import statistics
from pathlib import Path
from typing import Dict, List


def _round3(v: float | None) -> float | None:
    if v is None:
        return None
    return round(float(v), 3)


def _float(s: str):
    s = (s or "").strip()
    if s == "":
        return None
    if s.endswith("%"):
        s = s[:-1].strip()
    try:
        return float(s)
    except ValueError:
        return None


def _to_number_list(rows: List[Dict[str, str]], key: str) -> List[float]:
    vals: List[float] = []
    for row in rows:
        val = _float(row.get(key, ""))
        if val is not None and math.isfinite(val):
            vals.append(val)
    return vals


def _buildErrorRangeBuckets(
    values: List[float],
    range_edges: List[float],
    use_abs: bool = True,
) -> List[Dict[str, float | int | str]]:
    """按固定区间统计误差分布占比，并附加最后一个 >max 桶。"""
    if not values:
        return []
    if not range_edges or len(range_edges) < 2:
        return []

    normalized = [abs(v) if use_abs else v for v in values]
    total = len(normalized)
    buckets: List[Dict[str, float | int | str]] = []

    for i in range(len(range_edges) - 1):
        lo = float(range_edges[i])
        hi = float(range_edges[i + 1])
        count = sum(1 for v in normalized if lo <= v < hi)
        buckets.append(
            {
                "range": f"[{lo:g},{hi:g})",
                "lower": _round3(lo),
                "upper": _round3(hi),
                "count": count,
                "ratio": _round3((count / total) if total else 0.0),
            }
        )

    max_edge = float(range_edges[-1])
    tail_count = sum(1 for v in normalized if v >= max_edge)
    buckets.append(
        {
            "range": f">{max_edge:g}",
            "lower": _round3(max_edge),
            "upper": None,
            "count": tail_count,
            "ratio": _round3((tail_count / total) if total else 0.0),
        }
    )
    return buckets


def _quantile(values: List[float], q: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    if q <= 0:
        return min(values)
    if q >= 1:
        return max(values)
    sorted_vals = sorted(values)
    pos = (len(sorted_vals) - 1) * q
    lower = int(math.floor(pos))
    upper = int(math.ceil(pos))
    if lower == upper:
        return sorted_vals[lower]
    weight = pos - lower
    return sorted_vals[lower] * (1 - weight) + sorted_vals[upper] * weight


def _pearson_corr(a: List[float], b: List[float]) -> float | None:
    if len(a) != len(b) or len(a) < 2:
        return None
    mean_a = statistics.fmean(a)
    mean_b = statistics.fmean(b)
    num = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b))
    den_a = math.sqrt(sum((x - mean_a) ** 2 for x in a))
    den_b = math.sqrt(sum((y - mean_b) ** 2 for y in b))
    den = den_a * den_b
    if den == 0:
        return None
    return num / den


def compute_stats(
    rows: List[Dict[str, str]],
    threshold: float = 10.0,
    golden_file: str = "",
    test_file: str = "",
) -> Dict:
    """
    统计对比结果中的比例列与关键差值列。

    - ratio 列（arrival/required/slack）按百分比统计
    - 段级 diff 列（launch/data delay、CRP/uncertainty）按绝对值统计
    """
    # 比例列固定为现有实现，以保持兼容
    ratio_columns = ["arrival_time_ratio", "required_time_ratio", "slack_diff"]

    stats_by_col: Dict[str, Dict] = {}
    for col in ratio_columns:
        vals = _to_number_list(rows, col)
        if vals:
            col_stats = {
                "count": len(vals),
                "min": _round3(min(vals)),
                "max": _round3(max(vals)),
                "mean": _round3(statistics.fmean(abs(v) for v in vals)),
                "median": _round3(statistics.median(vals)),
                "std": _round3(statistics.stdev(vals) if len(vals) > 1 else 0.0),
                "p90": _round3(_quantile(vals, 0.9)),
                "p95": _round3(_quantile(vals, 0.95)),
                "p99": _round3(_quantile(vals, 0.99)),
            }
            exceed = [v for v in vals if abs(v) > threshold]
            col_stats["threshold"] = {
                "value": _round3(threshold),
                "count": len(exceed),
                "ratio": _round3((len(exceed) / len(vals)) if vals else 0.0),
            }
        else:
            col_stats = {
                "count": 0,
                "min": None,
                "max": None,
                "mean": None,
                "median": None,
                "std": None,
                "p90": None,
                "p95": None,
                "p99": None,
                "threshold": {"value": _round3(threshold), "count": 0, "ratio": 0.0},
            }
        stats_by_col[col] = col_stats

    data_by_col = {col: _to_number_list(rows, col) for col in ratio_columns}
    correlations: Dict[str, Dict] = {}
    for c1, c2 in [
        ("arrival_time_ratio", "required_time_ratio"),
        ("arrival_time_ratio", "slack_diff"),
        ("required_time_ratio", "slack_diff"),
    ]:
        pair_vals = [
            (_float(row.get(c1, "")), _float(row.get(c2, "")))
            for row in rows
            if _float(row.get(c1, "")) is not None and _float(row.get(c2, "")) is not None
        ]
        xs = [v[0] for v in pair_vals]
        ys = [v[1] for v in pair_vals]
        correlations[f"{c1}__{c2}"] = {
            "count": len(pair_vals),
            "pearson": _round3(_pearson_corr(xs, ys)),
        }

    # 段级差值统计（launch/data delay + CRP/uncertainty），给出整体差异轮廓
    segment_diff_columns = [
        "launch_clock_delay_diff",
        "data_path_delay_diff",
        "clock_reconvergence_pessimism_diff",
        "clock_uncertainty_diff",
    ]
    segment_stats: Dict[str, Dict] = {}
    for col in segment_diff_columns:
        vals = _to_number_list(rows, col)
        if vals:
            ss = {
                "count": len(vals),
                "min": _round3(min(vals)),
                "max": _round3(max(vals)),
                "mean": _round3(statistics.fmean(vals)),
                "median": _round3(statistics.median(vals)),
                "std": _round3(statistics.stdev(vals) if len(vals) > 1 else 0.0),
                "p90": _round3(_quantile(vals, 0.9)),
                "p95": _round3(_quantile(vals, 0.95)),
                "p99": _round3(_quantile(vals, 0.99)),
            }
        else:
            ss = {
                "count": 0,
                "min": None,
                "max": None,
                "mean": None,
                "median": None,
                "std": None,
                "p90": None,
                "p95": None,
                "p99": None,
            }
        segment_stats[col] = ss

    # slack PASS/FAIL 统计（来自 compare_result.csv 中的 slack_pass）
    slack_pass_count = sum(1 for r in rows if (r.get("slack_pass") or "").strip().upper() == "PASS")
    slack_fail_count = sum(1 for r in rows if (r.get("slack_pass") or "").strip().upper() == "FAIL")
    slack_total = slack_pass_count + slack_fail_count
    slack_unknown_count = max(0, len(rows) - slack_total)
    slack_pass_ratio = (slack_pass_count / slack_total) if slack_total else 0.0

    # 新增：误差分桶占比统计
    error_range_stats = {
        "arrival_time_ratio": {
            "abs_value": True,
            "ranges": [0, 5, 10, 20, 50],
            "unit": "%",
            "bins": _buildErrorRangeBuckets(
                _to_number_list(rows, "arrival_time_ratio"),
                range_edges=[0, 5, 10, 20, 50],
                use_abs=True,
            ),
        },
        "required_time_ratio": {
            "abs_value": True,
            "ranges": [0, 5, 10, 20, 50],
            "unit": "%",
            "bins": _buildErrorRangeBuckets(
                _to_number_list(rows, "required_time_ratio"),
                range_edges=[0, 5, 10, 20, 50],
                use_abs=True,
            ),
        },
        "slack_diff": {
            "abs_value": True,
            "ranges": [0, 5, 10, 20],
            "unit": "abs",
            "bins": _buildErrorRangeBuckets(
                _to_number_list(rows, "slack_diff"),
                range_edges=[0, 5, 10, 20],
                use_abs=True,
            ),
        },
    }

    return {
        "input_files": {
            "golden_file": str(golden_file or ""),
            "test_file": str(test_file or ""),
        },
        "sample_count": len(rows),
        "metrics": stats_by_col,
        "segment_metrics": segment_stats,
        "correlations": correlations,
        "columns": ratio_columns,
        "numeric_counts": {k: len(v) for k, v in data_by_col.items()},
        "error_range_stats": error_range_stats,
        "slack_pass_stats": {
            "pass_count": slack_pass_count,
            "fail_count": slack_fail_count,
            "unknown_count": slack_unknown_count,
            "pass_ratio": slack_pass_ratio,
        },
    }


def write_stats_json(stats: Dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)


def write_stats_csv(stats: Dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "metric",
        "count",
        "min",
        "max",
        "mean",
        "median",
        "std",
        "p90",
        "p95",
        "p99",
        "threshold_value",
        "threshold_count",
        "threshold_ratio",
    ]
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for metric, data in stats.get("metrics", {}).items():
            threshold_info = data.get("threshold", {})
            writer.writerow(
                {
                    "metric": metric,
                    "count": data.get("count"),
                    "min": data.get("min"),
                    "max": data.get("max"),
                    "mean": data.get("mean"),
                    "median": data.get("median"),
                    "std": data.get("std"),
                    "p90": data.get("p90"),
                    "p95": data.get("p95"),
                    "p99": data.get("p99"),
                    "threshold_value": threshold_info.get("value"),
                    "threshold_count": threshold_info.get("count"),
                    "threshold_ratio": threshold_info.get("ratio"),
                }
            )

