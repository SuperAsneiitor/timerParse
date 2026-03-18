from __future__ import annotations

import html as html_module
from pathlib import Path
from typing import Dict, List, Optional

from .path_detail_html import generatePathDetailPage


def _fmt_percent_value(v):
    if v is None:
        return "N/A"
    return f"{float(v):.3f}%"


def _fmt_plain(v):
    if v is None:
        return "N/A"
    return str(v)


def _detailFileName(row: Dict[str, str]) -> str:
    g = (row.get("path_id") or "").strip()
    t = (row.get("path_id_test") or g).strip()
    if g == t:
        return f"path_{g}.html"
    return f"path_g{g}_t{t}.html"


def generate_html_report(
    html_path: Path,
    golden_path: Path,
    test_path: Path,
    compared_count: int,
    stats: Dict,
    chart_files: Dict[str, str],
    charts_dir: Path,
    rows: List[Dict[str, str]],
    golden_launch_by_path_id: Optional[Dict[str, List[dict]]] = None,
    test_launch_by_path_id: Optional[Dict[str, List[dict]]] = None,
    golden_capture_by_path_id: Optional[Dict[str, List[dict]]] = None,
    test_capture_by_path_id: Optional[Dict[str, List[dict]]] = None,
) -> None:
    """
    生成路径级对比 HTML 报告。

    结构：
    - 基本信息（输入文件、样本数）
    - 比例列统计摘要 + 阈值超限摘要 + 相关性摘要
    - 段级差值统计（launch/data delay + CRP/uncertainty）
    - 简要路径列表（每条路径一行，可在后续版本扩展为点击查看明细）
    - 图表区域（hist/boxplot/scatter）
    """
    html_path.parent.mkdir(parents=True, exist_ok=True)

    # 统计摘要（ratio 列）
    rows_stats = []
    for metric, data in stats.get("metrics", {}).items():
        rows_stats.append(
            f"<tr><td>{metric}</td><td>{_fmt_plain(data.get('count'))}</td><td>{_fmt_percent_value(data.get('min'))}</td>"
            f"<td>{_fmt_percent_value(data.get('max'))}</td><td>{_fmt_percent_value(data.get('mean'))}</td><td>{_fmt_percent_value(data.get('median'))}</td>"
            f"<td>{_fmt_percent_value(data.get('std'))}</td><td>{_fmt_percent_value(data.get('p90'))}</td><td>{_fmt_percent_value(data.get('p95'))}</td>"
            f"<td>{_fmt_percent_value(data.get('p99'))}</td></tr>"
        )

    # 阈值超限摘要
    rows_threshold = []
    for metric, data in stats.get("metrics", {}).items():
        t = data.get("threshold", {})
        rows_threshold.append(
            f"<tr><td>{metric}</td><td>{_fmt_percent_value(t.get('value'))}</td><td>{_fmt_plain(t.get('count'))}</td>"
            f"<td>{_fmt_percent_value((t.get('ratio') or 0.0) * 100)}</td></tr>"
        )

    # 相关性摘要
    rows_corr = []
    for pair, data in stats.get("correlations", {}).items():
        rows_corr.append(
            f"<tr><td>{pair}</td><td>{data.get('count')}</td><td>{data.get('pearson')}</td></tr>"
        )

    # 段级差值统计（launch/data delay + CRP/uncertainty）
    rows_segment_stats = []
    for metric, data in (stats.get("segment_metrics") or {}).items():
        rows_segment_stats.append(
            f"<tr><td>{metric}</td><td>{_fmt_plain(data.get('count'))}</td>"
            f"<td>{_fmt_plain(data.get('min'))}</td><td>{_fmt_plain(data.get('max'))}</td>"
            f"<td>{_fmt_plain(data.get('mean'))}</td><td>{_fmt_plain(data.get('median'))}</td>"
            f"<td>{_fmt_plain(data.get('std'))}</td><td>{_fmt_plain(data.get('p90'))}</td>"
            f"<td>{_fmt_plain(data.get('p95'))}</td><td>{_fmt_plain(data.get('p99'))}</td></tr>"
        )

    # 路径列表（简单表格：path_id/startpoint/endpoint/slack_ratio/launch/data delay diff）
    # 同时为每条路径生成独立的详细对比页面，并在此处加上可点击链接。
    detail_dir = html_path.parent / "paths"
    rows_paths = []
    for row in rows:
        pid = (row.get("path_id") or "").strip()
        pid_t = (row.get("path_id_test") or pid).strip()
        if pid:
            fname = _detailFileName(row)
            detail_html = detail_dir / fname
            gl = (
                golden_launch_by_path_id.get(pid, [])
                if golden_launch_by_path_id
                else None
            )
            tl = (
                test_launch_by_path_id.get(pid_t, [])
                if test_launch_by_path_id
                else None
            )
            gc = (
                golden_capture_by_path_id.get(pid, [])
                if golden_capture_by_path_id
                else None
            )
            tc = (
                test_capture_by_path_id.get(pid_t, [])
                if test_capture_by_path_id
                else None
            )
            generatePathDetailPage(
                row=row,
                html_path=detail_html,
                golden_path=golden_path,
                test_path=test_path,
                golden_launch_rows=gl,
                test_launch_rows=tl,
                golden_capture_rows=gc,
                test_capture_rows=tc,
            )
            pid_cell = f"<a href='paths/{fname}' target='_blank'>{html_module.escape(pid)}</a>"
        else:
            pid_cell = ""

        rows_paths.append(
            "<tr>"
            f"<td>{pid_cell}</td>"
            f"<td>{_fmt_plain(row.get('startpoint'))}</td>"
            f"<td>{_fmt_plain(row.get('endpoint'))}</td>"
            f"<td>{_fmt_plain(row.get('slack_ratio'))}</td>"
            f"<td>{_fmt_plain(row.get('launch_clock_delay_diff'))}</td>"
            f"<td>{_fmt_plain(row.get('data_path_delay_diff'))}</td>"
            f"<td>{_fmt_plain(row.get('clock_reconvergence_pessimism_diff'))}</td>"
            f"<td>{_fmt_plain(row.get('clock_uncertainty_diff'))}</td>"
            "</tr>"
        )

    chart_tags = []
    for key, name in chart_files.items():
        rel = Path(charts_dir.name) / name
        chart_tags.append(
            f"<h3>{key}</h3><img src='{rel.as_posix()}' alt='{key}' style='max-width:100%;height:auto;' />"
        )

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

  <h2>统计摘要（比例列）</h2>
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

  <h2>段级差值摘要（launch/data delay 与 CRP/uncertainty）</h2>
  <table>
    <tr><th>metric</th><th>count</th><th>min</th><th>max</th><th>mean</th><th>median</th><th>std</th><th>p90</th><th>p95</th><th>p99</th></tr>
    {''.join(rows_segment_stats)}
  </table>

  <h2>路径列表（每条路径的核心差异）</h2>
  <table>
    <tr><th>path_id</th><th>startpoint</th><th>endpoint</th><th>slack_ratio</th><th>launch_clock_delay_diff</th><th>data_path_delay_diff</th><th>CRP_diff</th><th>uncertainty_diff</th></tr>
    {''.join(rows_paths)}
  </table>

  <h2>图表</h2>
  {''.join(chart_tags) if chart_tags else '<p>未生成图表。</p>'}
</body>
</html>
"""
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

