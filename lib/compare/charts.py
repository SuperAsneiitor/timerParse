from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from .. import log_util


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


def _to_number_list(rows: List[dict], key: str) -> List[float]:
    vals: List[float] = []
    for row in rows:
        val = _float(row.get(key, ""))
        if val is not None:
            vals.append(val)
    return vals


def _ensure_matplotlib() -> bool:
    try:
        import matplotlib  # noqa: F401

        return True
    except Exception:
        log_util.error("matplotlib 未安装，尝试自动安装...")
        try:
            import subprocess
            import sys

            subprocess.check_call([sys.executable, "-m", "pip", "install", "matplotlib"])
            import matplotlib  # noqa: F401

            log_util.error("matplotlib 自动安装成功。")
            return True
        except Exception as e:
            log_util.error(f"警告: matplotlib 安装失败，将跳过图表生成。错误: {e}")
            return False


def generate_charts(
    rows: List[dict],
    charts_dir: Path,
    bins: int = 50,
    ratio_columns: List[str] | None = None,
) -> Dict[str, str]:
    """基于关键数值列生成直方图/箱线图/散点图，帮助观察总体差异分布。"""
    if not _ensure_matplotlib():
        return {}
    import matplotlib.pyplot as plt

    if ratio_columns is None:
        ratio_columns = ["arrival_time_ratio", "required_time_ratio", "slack_diff"]

    charts_dir.mkdir(parents=True, exist_ok=True)
    chart_files: Dict[str, str] = {}
    data = {col: _to_number_list(rows, col) for col in ratio_columns}

    # 各关键列直方图
    for col in ratio_columns:
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

    # 箱线图
    box_data = [data[col] for col in ratio_columns if data[col]]
    box_labels = [col for col in ratio_columns if data[col]]
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

    # 关键列之间散点图
    for x_col, y_col in [
        ("arrival_time_ratio", "required_time_ratio"),
        ("arrival_time_ratio", "slack_diff"),
        ("required_time_ratio", "slack_diff"),
    ]:
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

