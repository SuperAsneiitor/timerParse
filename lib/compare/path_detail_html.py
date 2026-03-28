"""单条 Timing Path 的 HTML 详情页（汇总 + 可选 launch/capture 逐点对比）。"""
from __future__ import annotations

import html as html_module
import re
from pathlib import Path
from typing import Dict, List, Optional


def _fmt(v: object) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.4f}"
    s = str(v)
    # 仅对本身带小数点的数值字符串做 4 位小数格式化，避免 path_id 等整数被改写。
    if "." in s:
        f = _parseFloat(s)
        if f is not None:
            return f"{f:.4f}"
    return s


def _normalizePointForCompare(point: str) -> str:
    """逐点对比时统一 point 文本，去除 PT 的方向箭头噪声。"""
    p = (point or "").strip()
    if not p:
        return ""
    p = p.replace("<-", " ").replace("->", " ")
    p = re.sub(r"\s+", " ", p).strip()
    return p


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
    return f"{tf - gf:.4f}"


# 逐点对比时展示的统一语义列：
# - StepDelay: format1/pt 的 Incr == format2 的 Delay
# - PathTime:  format1/pt 的 Path == format2 的 Time
_POINT_METRIC_SPECS = [
    ("Cap", "Cap"),
    ("Derate", "Derate"),
    ("Trans", "Trans"),
    ("Incr", "Incr"),
    ("Time", "Time"),
    ("trigger_edge", "trigger_edge"),
]


def _metricValue(row: dict, key: str) -> str:
    if key == "Incr":
        return str(row.get("Incr") or row.get("Delay") or row.get("StepDelay") or "")
    if key == "Time":
        return str(row.get("Time") or row.get("Path") or row.get("PathTime") or "")
    return str(row.get(key, "") or "")


def _trimCaptureSummaryTail(rows: List[dict]) -> List[dict]:
    """
    裁掉 capture 段末尾 summary 行（format1/format2 常见），避免与 PT 逐点对比产生无意义噪声。
    """
    if not rows:
        return rows
    summary_prefixes = (
        "path check period",
        "clock reconvergence pessimism",
        "clock uncertainty",
        "data required time",
        "slack",
    )
    end = len(rows)
    while end > 0:
        p = _normalizePointForCompare(str(rows[end - 1].get("point") or "")).lower()
        if any(p.startswith(prefix) for prefix in summary_prefixes):
            end -= 1
            continue
        break
    return rows[:end]


def _alignRowsForFormat1Gap(rows_g: List[dict], rows_t: List[dict]) -> tuple[List[dict], List[dict]]:
    """
    对齐逐点比较：
    - format1 的 port 通常只有一行；
    - 与其它格式比较时若总行数差 1，允许在 format1 侧插入一行空白占位，减少后续行整体错位。
    """
    if abs(len(rows_g) - len(rows_t)) != 1:
        return rows_g, rows_t
    if len(rows_g) > len(rows_t):
        long_rows, short_rows, short_is_g = rows_g, rows_t, False
    else:
        long_rows, short_rows, short_is_g = rows_t, rows_g, True

    # 仅在短侧明确是 format1 时才插空；避免把 PT/format2 误判后引入新的错位。
    # format1 的逐点行通常带有 Location 字段（可能为空字符串，但键存在）。
    if not any("Location" in row for row in short_rows):
        return rows_g, rows_t

    # 使用 format1 端口文本特征（全角括号）定位占位插入点
    ins = -1
    for i, row in enumerate(short_rows):
        point = (row.get("point") or "").strip()
        if "（propagated)" in point:
            ins = i + 1
            break
    if ins < 0:
        return rows_g, rows_t
    padded = short_rows[:ins] + [{}] + short_rows[ins:]
    if short_is_g:
        return padded, long_rows
    return long_rows, padded


def _alignRowsByPointSequence(rows_g: List[dict], rows_t: List[dict]) -> tuple[List[dict], List[dict]]:
    """
    基于 point 文本做全局序列对齐：
    - 相同 point 视为 match；
    - 允许在任一侧插入空白行（gap），避免局部插删导致后续整体错位。
    """
    def _pointAlignKey(row: dict) -> str:
        """生成逐点对齐键：弱化格式噪声，保留语义锚点。"""
        point = str(row.get("point") or "").strip().lower()
        if not point:
            return ""
        # 去掉方向箭头/收尾符，避免同一点因符号不同错位
        point = point.replace("<-", " ").replace("->", " ")
        # 统一全角/半角括号与空白
        point = point.replace("（", "(").replace("）", ")")
        point = re.sub(r"\s+", " ", point).strip()
        # pin 名对齐时忽略末尾 cell 类型后缀：u11/CK (XXX) ~= u11/CK
        if "/" in point:
            point = re.sub(r"\s*\([^)]*\)\s*$", "", point).strip()

        # 关键语义锚点：尾部行按语义归并
        if "clock reconvergence pessimism" in point:
            return "anchor:clock_reconvergence_pessimism"
        if "clock uncertainty" in point:
            return "anchor:clock_uncertainty"
        if "path check period" in point:
            return "anchor:path_check_period"
        if "data arrival time" in point:
            return "anchor:data_arrival_time"
        if "data required time" in point:
            return "anchor:data_required_time"

        return point

    points_g = [_pointAlignKey(row) for row in rows_g]
    points_t = [_pointAlignKey(row) for row in rows_t]
    n, m = len(points_g), len(points_t)

    # dp[i][j] = 对齐前 i/j 个元素的最小代价
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    prev: List[List[tuple[int, int] | None]] = [[None] * (m + 1) for _ in range(n + 1)]

    for i in range(1, n + 1):
        dp[i][0] = i
        prev[i][0] = (i - 1, 0)
    for j in range(1, m + 1):
        dp[0][j] = j
        prev[0][j] = (0, j - 1)

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            sub_cost = 0 if points_g[i - 1] == points_t[j - 1] else 2
            cand_sub = dp[i - 1][j - 1] + sub_cost
            cand_del = dp[i - 1][j] + 1
            cand_ins = dp[i][j - 1] + 1
            best = cand_sub
            prev_pos = (i - 1, j - 1)
            if cand_del < best:
                best = cand_del
                prev_pos = (i - 1, j)
            if cand_ins < best:
                best = cand_ins
                prev_pos = (i, j - 1)
            dp[i][j] = best
            prev[i][j] = prev_pos

    aligned_g: List[dict] = []
    aligned_t: List[dict] = []
    i, j = n, m
    while i > 0 or j > 0:
        p = prev[i][j]
        if p is None:
            break
        pi, pj = p
        if pi == i - 1 and pj == j - 1:
            aligned_g.append(rows_g[i - 1])
            aligned_t.append(rows_t[j - 1])
        elif pi == i - 1 and pj == j:
            aligned_g.append(rows_g[i - 1])
            aligned_t.append({})
        else:
            aligned_g.append({})
            aligned_t.append(rows_t[j - 1])
        i, j = pi, pj

    aligned_g.reverse()
    aligned_t.reverse()
    return aligned_g, aligned_t


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
    if "capture" in (title or "").strip().lower():
        rows_g = _trimCaptureSummaryTail(rows_g)
        rows_t = _trimCaptureSummaryTail(rows_t)
    rows_g, rows_t = _alignRowsForFormat1Gap(rows_g, rows_t)
    rows_g, rows_t = _alignRowsByPointSequence(rows_g, rows_t)
    n = max(len(rows_g), len(rows_t))
    header_top = (
        "<tr><th rowspan='2' scope='col'>idx</th>"
        "<th rowspan='2' scope='col'>Point (G)</th>"
        "<th rowspan='2' scope='col'>Point (T)</th>"
        + "".join(
            f"<th colspan='3' scope='colgroup'>{html_module.escape(label)}</th>"
            for label, _ in _POINT_METRIC_SPECS
        )
        + "</tr>"
    )
    header_sub = "<tr>" + "".join("<th scope='col'>G</th><th scope='col'>T</th><th scope='col'>Δ</th>" for _ in _POINT_METRIC_SPECS) + "</tr>"
    body: List[str] = []
    for i in range(n):
        rg = rows_g[i] if i < len(rows_g) else {}
        rt = rows_t[i] if i < len(rows_t) else {}
        pg = _normalizePointForCompare(str(rg.get("point") or ""))
        pt = _normalizePointForCompare(str(rt.get("point") or ""))
        mismatch = pg != pt and (pg or pt)
        row_class = " class='point-compare-row-mismatch'" if mismatch else ""
        cells = [
            f"<td>{i}</td>",
            f"<td>{html_module.escape(pg)}</td>",
            f"<td>{html_module.escape(pt)}</td>",
        ]
        for _label, key in _POINT_METRIC_SPECS:
            gv = _metricValue(rg, key)
            tv = _metricValue(rt, key)
            cells.append(f"<td>{html_module.escape(_fmt(gv))}</td>")
            cells.append(f"<td>{html_module.escape(_fmt(tv))}</td>")
            cells.append(f"<td>{html_module.escape(_numDiff(_fmt(gv), _fmt(tv)))}</td>")
        body.append(f"<tr{row_class}>{''.join(cells)}</tr>")
    return (
        f"<h2>{html_module.escape(title)}</h2>"
        "<p>黄色行表示同索引下 Point 文本不一致（结构或拓扑可能不同）。</p>"
        "<div class='point-compare-wrap'>"
        "<table class='point-compare'>"
        f"<thead>{header_top}{header_sub}</thead><tbody>{''.join(body)}</tbody>"
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

    /* 逐点对比：独立滚动区 + 双层表头 sticky（border-collapse: separate 利于 sticky 兼容） */
    .point-compare-wrap {{
      overflow: auto;
      max-height: min(80vh, 900px);
      margin-bottom: 18px;
      -webkit-overflow-scrolling: touch;
    }}
    .point-compare {{
      border-collapse: separate;
      border-spacing: 0;
      width: 100%;
      margin-bottom: 0;
    }}
    .point-compare th,
    .point-compare td {{
      border-style: solid;
      border-color: #ccc;
      border-width: 0 1px 1px 0;
      padding: 6px 8px;
      font-size: 12px;
      vertical-align: top;
    }}
    .point-compare tbody td {{
      background: #fff;
    }}
    .point-compare tbody tr.point-compare-row-mismatch td {{
      background: #fff3cd;
    }}
    .point-compare thead tr:first-child th {{
      border-top-width: 1px;
    }}
    .point-compare tr > :first-child {{
      border-left-width: 1px;
    }}
    .point-compare thead th {{
      background: #f3f3f3;
      text-align: left;
      position: sticky;
      z-index: 2;
    }}
    /* 第一行分组表头：贴容器/视口顶 */
    .point-compare thead tr:first-child th {{
      top: 0;
      z-index: 3;
      box-shadow: 0 1px 0 #bbb;
    }}
    /* idx / Point 两列跨两行，压在分组表头之上 */
    .point-compare thead tr:first-child th[rowspan='2'] {{
      z-index: 5;
    }}
    /* 第二行 G/T/Δ：叠在第一行之下沿 */
    .point-compare thead tr:nth-child(2) th {{
      top: 34px;
      z-index: 4;
      box-shadow: 0 1px 0 #bbb;
    }}
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
