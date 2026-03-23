"""单条 Timing Path 的 HTML 详情页（汇总 + 可选 launch/capture 逐点对比）。"""
from __future__ import annotations

import html as html_module
from pathlib import Path
from typing import Dict, List, Optional


def _fmt(v: object) -> str:
    if v is None:
        return ""
    return str(v)


def _parseFloat(s: str) -> float | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _numDiff(g: str, t: str) -> str:
    gf, tf = _parseFloat(g), _parseFloat(t)
    if gf is None or tf is None:
        return ""
    return f"{tf - gf:.6f}"


# 逐点对比时优先展示的列（两侧 CSV 均可能存在的语义列）
_POINT_METRIC_KEYS = [
    "Type",
    "Fanout",
    "Cap",
    "Trans",
    "Delay",
    "Incr",
    "Time",
    "Path",
    "trigger_edge",
    "Description",
]


def buildPointSegmentHtml(
    title: str,
    rows_g: Optional[List[dict]],
    rows_t: Optional[List[dict]],
) -> str:
    """生成 launch 或 capture 段的逐点对比表 HTML。"""
    if not rows_g and not rows_t:
        return f"<h2>{html_module.escape(title)}</h2><p>无数据。</p>"
    rows_g = rows_g or []
    rows_t = rows_t or []
    n = max(len(rows_g), len(rows_t))
    header = (
        "<tr><th>idx</th><th>Point (G)</th><th>Point (T)</th>"
        + "".join(f"<th>{html_module.escape(k)} G</th><th>{html_module.escape(k)} T</th><th>Δ</th>" for k in _POINT_METRIC_KEYS)
        + "</tr>"
    )
    body: List[str] = []
    for i in range(n):
        rg = rows_g[i] if i < len(rows_g) else {}
        rt = rows_t[i] if i < len(rows_t) else {}
        pg = (rg.get("point") or "").strip()
        pt = (rt.get("point") or "").strip()
        mismatch = pg != pt and (pg or pt)
        row_style = " style='background:#fff3cd'" if mismatch else ""
        cells = [
            f"<td>{i}</td>",
            f"<td>{html_module.escape(pg)}</td>",
            f"<td>{html_module.escape(pt)}</td>",
        ]
        for key in _POINT_METRIC_KEYS:
            gv = rg.get(key, "")
            tv = rt.get(key, "")
            cells.append(f"<td>{html_module.escape(_fmt(gv))}</td>")
            cells.append(f"<td>{html_module.escape(_fmt(tv))}</td>")
            cells.append(f"<td>{html_module.escape(_numDiff(_fmt(gv), _fmt(tv)))}</td>")
        body.append(f"<tr{row_style}>{''.join(cells)}</tr>")
    return (
        f"<h2>{html_module.escape(title)}</h2>"
        "<p>黄色行表示同索引下 Point 文本不一致（结构或拓扑可能不同）。</p>"
        "<div style='overflow-x:auto'>"
        "<table>"
        f"{header}{''.join(body)}"
        "</table></div>"
    )


def generatePathDetailPage(
    row: Dict[str, str],
    html_path: Path,
    golden_path: Path,
    test_path: Path,
    golden_launch_rows: Optional[List[dict]] = None,
    test_launch_rows: Optional[List[dict]] = None,
    golden_capture_rows: Optional[List[dict]] = None,
    test_capture_rows: Optional[List[dict]] = None,
) -> None:
    """生成单条路径的详细对比页面。"""
    html_path.parent.mkdir(parents=True, exist_ok=True)

    pid = row.get("path_id", "")
    pid_t = row.get("path_id_test") or pid
    startpoint = row.get("startpoint", "")
    endpoint = row.get("endpoint", "")
    path_type = row.get("path_type", "")
    start_ck = row.get("startpoint_clock", "")
    end_ck = row.get("endpoint_clock", "")

    def cell(label: str, g_key: str, t_key: str, diff_key: str | None = None) -> str:
        g = row.get(g_key, "")
        t = row.get(t_key, "")
        d = row.get(diff_key, "") if diff_key else ""
        return (
            "<tr>"
            f"<td>{html_module.escape(label)}</td>"
            f"<td>{html_module.escape(_fmt(g))}</td>"
            f"<td>{html_module.escape(_fmt(t))}</td>"
            f"<td>{html_module.escape(_fmt(d))}</td>"
            "</tr>"
        )

    rows_main = [
        cell("Arrival time", "arrival_time_golden", "arrival_time_test", "arrival_time_ratio"),
        cell("Required time", "required_time_golden", "required_time_test", "required_time_ratio"),
        cell("Slack", "slack_golden", "slack_test", "slack_diff"),
    ]
    rows_seg = [
        cell("Launch clock delay", "launch_clock_delay_golden", "launch_clock_delay_test", "launch_clock_delay_diff"),
        cell("Data path delay", "data_path_delay_golden", "data_path_delay_test", "data_path_delay_diff"),
        cell(
            "Clock reconvergence pessimism",
            "clock_reconvergence_pessimism_golden",
            "clock_reconvergence_pessimism_test",
            "clock_reconvergence_pessimism_diff",
        ),
        cell(
            "Clock uncertainty",
            "clock_uncertainty_golden",
            "clock_uncertainty_test",
            "clock_uncertainty_diff",
        ),
    ]

    def pt_cell(label: str, base: str) -> str:
        g = row.get(f"{base}_golden", "")
        t = row.get(f"{base}_test", "")
        d = row.get(f"{base}_diff", "")
        return (
            "<tr>"
            f"<td>{html_module.escape(label)}</td>"
            f"<td>{html_module.escape(_fmt(g))}</td>"
            f"<td>{html_module.escape(_fmt(t))}</td>"
            f"<td>{html_module.escape(_fmt(d))}</td>"
            "</tr>"
        )

    rows_pts = [
        pt_cell("Launch clock point count", "launch_clock_point_count"),
        pt_cell("Data path point count", "data_path_point_count"),
        pt_cell("Capture point count", "capture_point_count"),
    ]

    seg_launch = ""
    if golden_launch_rows is not None or test_launch_rows is not None:
        seg_launch = buildPointSegmentHtml("Launch path 逐点对比", golden_launch_rows, test_launch_rows)
    seg_capture = ""
    if golden_capture_rows is not None or test_capture_rows is not None:
        seg_capture = buildPointSegmentHtml("Capture path 逐点对比", golden_capture_rows, test_capture_rows)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>Path detail - {html_module.escape(pid)}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 20px; }}
    table {{ border-collapse: collapse; width: 100%; margin-bottom: 18px; }}
    th, td {{ border: 1px solid #ccc; padding: 6px 8px; font-size: 12px; }}
    th {{ background: #f3f3f3; text-align: left; }}
  </style>
</head>
<body>
  <h1>Timing Path 详细对比</h1>
  <p><b>path_id (golden):</b> {html_module.escape(_fmt(pid))}</p>
  <p><b>path_id (test):</b> {html_module.escape(_fmt(pid_t))}</p>
  <p><b>startpoint:</b> {html_module.escape(startpoint)}</p>
  <p><b>endpoint:</b> {html_module.escape(endpoint)}</p>
  <p><b>path_type:</b> {html_module.escape(path_type)}</p>
  <p><b>startpoint_clock:</b> {html_module.escape(start_ck)}</p>
  <p><b>endpoint_clock:</b> {html_module.escape(end_ck)}</p>
  <p><b>golden_file:</b> {html_module.escape(str(golden_path))}</p>
  <p><b>test_file:</b> {html_module.escape(str(test_path))}</p>

  <h2>路径级指标</h2>
  <table>
    <tr><th>Metric</th><th>Golden</th><th>Test</th><th>Diff/Ratio</th></tr>
    {''.join(rows_main)}
  </table>

  <h2>段级延迟与时钟相关调整</h2>
  <table>
    <tr><th>Metric</th><th>Golden</th><th>Test</th><th>Diff</th></tr>
    {''.join(rows_seg)}
  </table>

  <h2>分段点数统计</h2>
  <table>
    <tr><th>Segment</th><th>Golden</th><th>Test</th><th>Diff</th></tr>
    {''.join(rows_pts)}
  </table>
  {seg_launch}
  {seg_capture}
</body>
</html>
"""
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)


# 兼容旧函数名
def generate_path_detail_page(*args, **kwargs):  # noqa: ANN002
    return generatePathDetailPage(*args, **kwargs)
