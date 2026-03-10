#!/usr/bin/env python3
"""
对比两个 path_summary CSV 文件（golden vs test）。
按 path_id 对齐，对 arrival_time、required_time、slack 计算 (test - golden) / golden，输出对比结果 CSV。
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import subprocess
import sys
from pathlib import Path


RATIO_COLUMNS = ["arrival_time_ratio", "required_time_ratio", "slack_ratio"]
FIELDNAMES_FULL = [
    "path_id",
    "startpoint",
    "endpoint",
    "arrival_time_golden",
    "arrival_time_test",
    "arrival_time_ratio",
    "required_time_golden",
    "required_time_test",
    "required_time_ratio",
    "slack_golden",
    "slack_test",
    "slack_ratio",
]
FIELDNAMES_SIMPLE = ["path_id", "arrival_time_ratio", "required_time_ratio", "slack_ratio"]


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


def _ratio(test_val: float | None, golden_val: float | None) -> str:
    """(test - golden) / golden * 100%，golden 为 0 或空时返回空字符串。"""
    if golden_val is None or test_val is None:
        return ""
    if golden_val == 0:
        return ""
    return f"{((test_val - golden_val) / golden_val) * 100:.6f}%"


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


def _to_number_list(rows: list[dict], key: str) -> list[float]:
    vals = []
    for row in rows:
        val = _float(row.get(key, ""))
        if val is not None and math.isfinite(val):
            vals.append(val)
    return vals


def _quantile(values: list[float], q: float) -> float | None:
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


def _pearson_corr(a: list[float], b: list[float]) -> float | None:
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


def compute_stats(rows: list[dict], threshold: float = 10.0) -> dict:
    stats_by_col = {}
    for col in RATIO_COLUMNS:
        vals = _to_number_list(rows, col)
        if vals:
            col_stats = {
                "count": len(vals),
                "min": min(vals),
                "max": max(vals),
                "mean": statistics.fmean(vals),
                "median": statistics.median(vals),
                "std": statistics.stdev(vals) if len(vals) > 1 else 0.0,
                "p90": _quantile(vals, 0.9),
                "p95": _quantile(vals, 0.95),
                "p99": _quantile(vals, 0.99),
            }
            exceed = [v for v in vals if abs(v) > threshold]
            col_stats["threshold"] = {
                "value": threshold,
                "count": len(exceed),
                "ratio": (len(exceed) / len(vals)) if vals else 0.0,
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
                "threshold": {"value": threshold, "count": 0, "ratio": 0.0},
            }
        stats_by_col[col] = col_stats

    data_by_col = {col: _to_number_list(rows, col) for col in RATIO_COLUMNS}
    correlations = {}
    pairs = [
        ("arrival_time_ratio", "required_time_ratio"),
        ("arrival_time_ratio", "slack_ratio"),
        ("required_time_ratio", "slack_ratio"),
    ]
    for c1, c2 in pairs:
        pair_vals = [
            (_float(row.get(c1, "")), _float(row.get(c2, "")))
            for row in rows
            if _float(row.get(c1, "")) is not None and _float(row.get(c2, "")) is not None
        ]
        xs = [v[0] for v in pair_vals]
        ys = [v[1] for v in pair_vals]
        correlations[f"{c1}__{c2}"] = {
            "count": len(pair_vals),
            "pearson": _pearson_corr(xs, ys),
        }

    return {
        "sample_count": len(rows),
        "metrics": stats_by_col,
        "correlations": correlations,
        "columns": RATIO_COLUMNS,
        "numeric_counts": {k: len(v) for k, v in data_by_col.items()},
    }


def write_stats_json(stats: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)


def write_stats_csv(stats: dict, path: Path) -> None:
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


def _ensure_matplotlib() -> bool:
    try:
        import matplotlib  # noqa: F401

        return True
    except Exception:
        print("matplotlib 未安装，尝试自动安装...", file=sys.stderr)
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "matplotlib"])
            import matplotlib  # noqa: F401

            print("matplotlib 自动安装成功。", file=sys.stderr)
            return True
        except Exception as e:
            print(f"警告: matplotlib 安装失败，将跳过图表生成。错误: {e}", file=sys.stderr)
            return False


def generate_charts(rows: list[dict], charts_dir: Path, bins: int = 50) -> dict[str, str]:
    if not _ensure_matplotlib():
        return {}
    import matplotlib.pyplot as plt

    charts_dir.mkdir(parents=True, exist_ok=True)
    chart_files: dict[str, str] = {}

    data = {col: _to_number_list(rows, col) for col in RATIO_COLUMNS}

    for col in RATIO_COLUMNS:
        vals = data[col]
        if not vals:
            continue
        plt.figure(figsize=(8, 5))
        plt.hist(vals, bins=bins)
        plt.title(f"Histogram - {col}")
        plt.xlabel(col)
        plt.ylabel("Count")
        out = charts_dir / f"hist_{col}.png"
        plt.tight_layout()
        plt.savefig(out)
        plt.close()
        chart_files[f"hist_{col}"] = out.name

    box_data = [data[col] for col in RATIO_COLUMNS if data[col]]
    box_labels = [col for col in RATIO_COLUMNS if data[col]]
    if box_data:
        plt.figure(figsize=(8, 5))
        plt.boxplot(box_data, tick_labels=box_labels)
        plt.title("Boxplot - ratio columns")
        plt.ylabel("Value")
        out = charts_dir / "boxplot_ratios.png"
        plt.tight_layout()
        plt.savefig(out)
        plt.close()
        chart_files["boxplot"] = out.name

    scatter_pairs = [
        ("arrival_time_ratio", "required_time_ratio"),
        ("arrival_time_ratio", "slack_ratio"),
        ("required_time_ratio", "slack_ratio"),
    ]
    for x_col, y_col in scatter_pairs:
        points = []
        for row in rows:
            x = _float(row.get(x_col, ""))
            y = _float(row.get(y_col, ""))
            if x is None or y is None:
                continue
            points.append((x, y))
        if not points:
            continue
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        plt.figure(figsize=(8, 5))
        plt.scatter(xs, ys, s=12, alpha=0.7)
        plt.title(f"Scatter - {x_col} vs {y_col}")
        plt.xlabel(x_col)
        plt.ylabel(y_col)
        out = charts_dir / f"scatter_{x_col}_vs_{y_col}.png"
        plt.tight_layout()
        plt.savefig(out)
        plt.close()
        chart_files[f"scatter_{x_col}_vs_{y_col}"] = out.name

    return chart_files


def generate_html_report(
    html_path: Path,
    golden_path: Path,
    test_path: Path,
    compared_count: int,
    stats: dict,
    chart_files: dict[str, str],
    charts_dir: Path,
) -> None:
    def _fmt_percent_value(v: float | int | None) -> str:
        if v is None:
            return "N/A"
        return f"{float(v):.6f}%"

    def _fmt_plain(v: float | int | None) -> str:
        if v is None:
            return "N/A"
        return str(v)

    html_path.parent.mkdir(parents=True, exist_ok=True)
    rows_stats = []
    for metric, data in stats.get("metrics", {}).items():
        rows_stats.append(
            f"<tr><td>{metric}</td><td>{_fmt_plain(data.get('count'))}</td><td>{_fmt_percent_value(data.get('min'))}</td>"
            f"<td>{_fmt_percent_value(data.get('max'))}</td><td>{_fmt_percent_value(data.get('mean'))}</td><td>{_fmt_percent_value(data.get('median'))}</td>"
            f"<td>{_fmt_percent_value(data.get('std'))}</td><td>{_fmt_percent_value(data.get('p90'))}</td><td>{_fmt_percent_value(data.get('p95'))}</td>"
            f"<td>{_fmt_percent_value(data.get('p99'))}</td></tr>"
        )

    rows_threshold = []
    for metric, data in stats.get("metrics", {}).items():
        t = data.get("threshold", {})
        rows_threshold.append(
            f"<tr><td>{metric}</td><td>{_fmt_percent_value(t.get('value'))}</td><td>{_fmt_plain(t.get('count'))}</td>"
            f"<td>{_fmt_percent_value((t.get('ratio') or 0.0) * 100)}</td></tr>"
        )

    rows_corr = []
    for pair, data in stats.get("correlations", {}).items():
        rows_corr.append(
            f"<tr><td>{pair}</td><td>{data.get('count')}</td><td>{data.get('pearson')}</td></tr>"
        )

    chart_tags = []
    for key, name in chart_files.items():
        rel = Path(charts_dir.name) / name
        chart_tags.append(f"<h3>{key}</h3><img src='{rel.as_posix()}' alt='{key}' style='max-width:100%;height:auto;' />")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>compare_path_summary 报告</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 20px; }}
    table {{ border-collapse: collapse; width: 100%; margin-bottom: 18px; }}
    th, td {{ border: 1px solid #ccc; padding: 6px 8px; font-size: 13px; }}
    th {{ background: #f3f3f3; text-align: left; }}
  </style>
</head>
<body>
  <h1>compare_path_summary 报告</h1>
  <p><b>golden_file:</b> {golden_path}</p>
  <p><b>test_file:</b> {test_path}</p>
  <p><b>sample_count:</b> {compared_count}</p>

  <h2>统计摘要</h2>
  <table>
    <tr><th>metric</th><th>count</th><th>min</th><th>max</th><th>mean</th><th>median</th><th>std</th><th>p90</th><th>p95</th><th>p99</th></tr>
    {''.join(rows_stats)}
  </table>

  <h2>阈值超限摘要</h2>
  <table>
    <tr><th>metric</th><th>threshold</th><th>count</th><th>ratio</th></tr>
    {''.join(rows_threshold)}
  </table>

  <h2>相关性摘要</h2>
  <table>
    <tr><th>pair</th><th>count</th><th>pearson</th></tr>
    {''.join(rows_corr)}
  </table>

  <h2>图表</h2>
  {''.join(chart_tags) if chart_tags else '<p>未生成图表。</p>'}
</body>
</html>
"""
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="对比两个 path_summary CSV：按 path_id 对齐，计算 (test - golden) / golden * 100% 并输出 CSV。"
    )
    parser.add_argument("golden_file", help="Golden path_summary.csv 路径")
    parser.add_argument("test_file", help="Test path_summary.csv 路径")
    parser.add_argument("-o", "--output", default="", help="输出 CSV 路径，默认 golden 同目录下 compare_result.csv")
    parser.add_argument("--threshold", type=float, default=10.0, help="阈值统计条件 abs(ratio_percent) > threshold，默认 10（即 10%%）")
    parser.add_argument("--bins", type=int, default=50, help="直方图桶数，默认 50")
    parser.add_argument("--charts-dir", default="", help="图表输出目录，默认 <output_dir>/charts")
    parser.add_argument("--no-charts", action="store_true", help="禁用图表输出")
    parser.add_argument("--no-html", action="store_true", help="禁用 HTML 报告输出")
    parser.add_argument("--stats-json", default="", help="统计 JSON 输出路径，默认 <output_dir>/compare_stats.json")
    parser.add_argument("--stats-csv", default="", help="统计 CSV 输出路径，默认不输出")
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

    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES_FULL, extrasaction="ignore")
        w.writeheader()
        w.writerows(result)

    simple_path = out_path.parent / (out_path.stem + "_simple" + out_path.suffix)
    with open(simple_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES_SIMPLE, extrasaction="ignore")
        w.writeheader()
        w.writerows(result)

    stats = compute_stats(result, threshold=args.threshold)
    stats_json_path = Path(args.stats_json) if args.stats_json else (out_path.parent / "compare_stats.json")
    write_stats_json(stats, stats_json_path)

    stats_csv_path = Path(args.stats_csv) if args.stats_csv else None
    if stats_csv_path:
        write_stats_csv(stats, stats_csv_path)

    charts_dir = Path(args.charts_dir) if args.charts_dir else (out_path.parent / "charts")
    chart_files = {}
    if not args.no_charts:
        bins = args.bins if args.bins > 0 else 50
        chart_files = generate_charts(result, charts_dir=charts_dir, bins=bins)

    html_path = out_path.parent / "compare_report.html"
    if not args.no_html:
        generate_html_report(
            html_path=html_path,
            golden_path=golden_path,
            test_path=test_path,
            compared_count=len(result),
            stats=stats,
            chart_files=chart_files,
            charts_dir=charts_dir,
        )

    print(f"Compared {len(result)} path(s) -> {out_path}")
    print(f"Simplified -> {simple_path}")
    print(f"Stats JSON -> {stats_json_path}")
    if stats_csv_path:
        print(f"Stats CSV -> {stats_csv_path}")
    if not args.no_charts:
        print(f"Charts dir -> {charts_dir}")
    if not args.no_html:
        print(f"HTML report -> {html_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
