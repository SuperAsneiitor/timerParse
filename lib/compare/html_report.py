from __future__ import annotations

import html as html_module
import json
import math
from pathlib import Path
from typing import Dict, List, Optional

from .path_detail_html import generatePathDetailPage
from .. import log_util


def _fmt_percent_value(v):
    if v is None:
        return "N/A"
    return f"{float(v):.3f}%"


def _fmt_plain(v):
    if v is None:
        return "N/A"
    return str(v)


def _fmt_metric_value(metric: str, v):
    """slack_diff 用普通数值；其余沿用百分比显示。"""
    if metric == "slack_diff":
        return _fmt_plain(v)
    return _fmt_percent_value(v)


def _detailFileName(row: Dict[str, str]) -> str:
    g = (row.get("path_id") or "").strip()
    t = (row.get("path_id_test") or g).strip()
    if g == t:
        return f"path_{g}.html"
    return f"path_g{g}_t{t}.html"


def _to_float(s: object) -> float | None:
    v = ("" if s is None else str(s)).strip()
    if not v:
        return None
    if v.endswith("%"):
        v = v[:-1].strip()
    try:
        x = float(v)
        if not math.isfinite(x):
            return None
        return x
    except Exception:
        return None


def _sort_key_for_row(row: Dict[str, str], sort_by: str, sort_abs: bool) -> float:
    """
    sort_by: 支持 ratio/diff 字段名，如 slack_diff、data_path_delay_diff、clock_uncertainty_diff 等。
    返回值越大表示差异越大（用于默认降序排序）。
    """
    v = _to_float(row.get(sort_by, ""))
    if v is None:
        return float("-inf")
    return abs(v) if sort_abs else v


def _render_nav_links(current: int, total: int) -> str:
    if total <= 1:
        return ""
    links: List[str] = []
    prev_page = current - 1
    next_page = current + 1
    if prev_page >= 1:
        links.append(f"<a href='page_{prev_page:04d}.html'>上一页</a>")
    else:
        links.append("<span style='color:#888'>上一页</span>")
    links.append(f"<span style='margin:0 10px'>第 {current}/{total} 页</span>")
    if next_page <= total:
        links.append(f"<a href='page_{next_page:04d}.html'>下一页</a>")
    else:
        links.append("<span style='color:#888'>下一页</span>")
    return "<div style='margin:10px 0'>" + " ".join(links) + "</div>"


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
    page_size: int = 100,
    sort_by: str = "slack_diff",
    sort_abs: bool = True,
    detail_scope: str = "first_page",
    detail_top_n: int = 0,
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

    # 为 global_client 动态排序准备数据文件（避免本地 file:// 下 fetch/CORS 限制）
    # - compare_rows.json：按 plan 保留数据文件
    # - compare_rows_data.js：把数据注入 window 供页面脚本直接使用
    sort_options = [
        # ratio 列
        "arrival_time_ratio",
        "required_time_ratio",
        "slack_diff",
        # slack PASS 相关可用指标（数值/比值）
        "slack_diff",
        "AT_ref",
        "clock_period",
        "slack_diff_AT_ref_ratio",
        "slack_diff_clock_period_ratio",
        # 现有 diff 列
        "data_path_delay_diff",
        "launch_clock_delay_diff",
        "clock_uncertainty_diff",
        "clock_reconvergence_pessimism_diff",
        "data_path_point_count_diff",
        "launch_clock_point_count_diff",
        "capture_point_count_diff",
    ]
    rows_json_str = json.dumps(rows, ensure_ascii=False)
    rows_json_path = html_path.parent / "compare_rows.json"
    rows_js_path = html_path.parent / "compare_rows_data.js"
    rows_json_path.write_text(rows_json_str, encoding="utf-8")
    rows_js_path.write_text(f"window.__compare_rows = {rows_json_str};\n", encoding="utf-8")

    sort_options_html = "".join(
        f"<option value='{html_module.escape(opt)}'>{html_module.escape(opt)}</option>"
        for opt in sort_options
    )

    # global_client：排序/分页 UI 逻辑放到独立 JS 文件，避免在 f-string 里嵌入大量花括号导致语法错误
    compare_sort_ui_path = html_path.parent / "compare_sort_ui.js"
    compare_sort_ui_path.write_text(
        r"""
(function(){
  const PAGE_IDX = Number(window.__compare_sort_page_idx ?? 0);
  const PAGE_SIZE = Number(window.__compare_sort_page_size ?? 100);
  const DEFAULT_SORT_BY = window.__compare_sort_default_sort_by ?? "slack_diff";
  const DEFAULT_SORT_ABS = Boolean(window.__compare_sort_default_sort_abs ?? true);
  const DETAIL_HREF_PREFIX = window.__compare_sort_detail_prefix ?? "../paths/";

  const STORE_KEY_BY = "timerExtract_compare_sort_by";
  const STORE_KEY_ABS = "timerExtract_compare_sort_abs";

  const allRows = (window.__compare_rows || []);

  function parseNum(v){
    if(v === null || v === undefined) return NaN;
    const s = String(v).trim();
    if(!s) return NaN;
    if(s.endsWith("%")) return parseFloat(s.slice(0, -1));
    return parseFloat(s);
  }

  function detailFileName(row){
    const g = (row.path_id || "").trim();
    const t = (row.path_id_test || g).trim();
    if(g === t) return "path_" + g + ".html";
    return "path_g" + g + "_t" + t + ".html";
  }

  function escapeHtml(s){
    return String(s).replace(/[&<>"']/g, function(m){
      switch(m){
        case "&": return "&amp;";
        case "<": return "&lt;";
        case ">": return "&gt;";
        case "\"": return "&quot;";
        case "'": return "&#39;";
        default: return m;
      }
    });
  }

  function getSortBy(){
    return localStorage.getItem(STORE_KEY_BY) || DEFAULT_SORT_BY;
  }

  function getSortAbs(){
    return (localStorage.getItem(STORE_KEY_ABS) || (DEFAULT_SORT_ABS ? "1" : "0")) === "1";
  }

  function sortRows(rows, sortBy, sortAbs){
    const arr = rows.slice();
    arr.sort((a, b) => {
      const va = parseNum(a[sortBy]);
      const vb = parseNum(b[sortBy]);
      const ka = Number.isFinite(va) ? (sortAbs ? Math.abs(va) : va) : -Infinity;
      const kb = Number.isFinite(vb) ? (sortAbs ? Math.abs(vb) : vb) : -Infinity;
      return kb - ka;
    });
    return arr;
  }

  function renderTable(pageRows){
    let html = "<table><tr>"
      + "<th>path_id</th><th>startpoint</th><th>endpoint</th>"
      + "<th>slack_diff</th>"
      + "<th>data_path_delay_diff</th><th>launch_clock_delay_diff</th>"
      + "<th>clock_uncertainty_diff</th><th>CRP_diff</th>"
      + "<th>data_path_point_count_diff</th><th>launch_clock_point_count_diff</th><th>capture_point_count_diff</th>"
      + "</tr>";

    for(const row of pageRows){
      const pid = (row.path_id || "").trim();
      let pidCell = escapeHtml(pid);
      if(pid){
        const fname = detailFileName(row);
        pidCell = "<a href='" + DETAIL_HREF_PREFIX + fname + "' target='_blank'>" + escapeHtml(pid) + "</a>";
      }

      html += "<tr>"
        + "<td>" + pidCell + "</td>"
        + "<td>" + escapeHtml(row.startpoint || "") + "</td>"
        + "<td>" + escapeHtml(row.endpoint || "") + "</td>"
        + "<td>" + escapeHtml(row.slack_diff || "") + "</td>"
        + "<td>" + escapeHtml(row.data_path_delay_diff || "") + "</td>"
        + "<td>" + escapeHtml(row.launch_clock_delay_diff || "") + "</td>"
        + "<td>" + escapeHtml(row.clock_uncertainty_diff || "") + "</td>"
        + "<td>" + escapeHtml(row.clock_reconvergence_pessimism_diff || "") + "</td>"
        + "<td>" + escapeHtml(row.data_path_point_count_diff || "") + "</td>"
        + "<td>" + escapeHtml(row.launch_clock_point_count_diff || "") + "</td>"
        + "<td>" + escapeHtml(row.capture_point_count_diff || "") + "</td>"
        + "</tr>";
    }
    html += "</table>";
    return html;
  }

  function renderCurrent(){
    const sortBy = getSortBy();
    const sortAbs = getSortAbs();
    const sorted = sortRows(allRows, sortBy, sortAbs);
    const start = PAGE_IDX * PAGE_SIZE;
    const end = Math.min(start + PAGE_SIZE, sorted.length);
    const pageRows = sorted.slice(start, end);
    const container = document.getElementById("table-container");
    if(container) container.innerHTML = renderTable(pageRows);
  }

  function bindControls(){
    const sel = document.getElementById("sortBySelect");
    const chk = document.getElementById("sortAbsChk");
    if(sel){
      sel.value = getSortBy();
      sel.addEventListener("change", () => {
        localStorage.setItem(STORE_KEY_BY, sel.value);
        renderCurrent();
      });
    }
    if(chk){
      chk.checked = getSortAbs();
      chk.addEventListener("change", () => {
        localStorage.setItem(STORE_KEY_ABS, chk.checked ? "1" : "0");
        renderCurrent();
      });
    }
  }

  bindControls();
  renderCurrent();
})();
""",
        encoding="utf-8",
    )

    # 统计摘要（ratio 列）
    rows_stats = []
    for metric, data in stats.get("metrics", {}).items():
        rows_stats.append(
            f"<tr><td>{metric}</td><td>{_fmt_plain(data.get('count'))}</td><td>{_fmt_metric_value(metric, data.get('min'))}</td>"
            f"<td>{_fmt_metric_value(metric, data.get('max'))}</td><td>{_fmt_metric_value(metric, data.get('mean'))}</td><td>{_fmt_metric_value(metric, data.get('median'))}</td>"
            f"<td>{_fmt_metric_value(metric, data.get('std'))}</td><td>{_fmt_metric_value(metric, data.get('p90'))}</td><td>{_fmt_metric_value(metric, data.get('p95'))}</td>"
            f"<td>{_fmt_metric_value(metric, data.get('p99'))}</td></tr>"
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

    # 方案 B：关键差异列 + 排序 + 分页
    sort_by = (sort_by or "slack_diff").strip()
    if not sort_by:
        sort_by = "slack_diff"
    sorted_rows = sorted(
        rows,
        key=lambda r: _sort_key_for_row(r, sort_by=sort_by, sort_abs=sort_abs),
        reverse=True,
    )

    if page_size <= 0:
        page_size = 100
    total_pages = (len(sorted_rows) + page_size - 1) // page_size
    pages_dir = html_path.parent / "pages"
    detail_dir = html_path.parent / "paths"
    pages_dir.mkdir(parents=True, exist_ok=True)

    generated_detail_count = 0

    def _row_should_generate_detail(page_idx: int, row_offset_in_page: int) -> bool:
        """按 detail_scope 决定某一行是否生成 detail 页。"""
        if detail_scope == "none":
            return False
        if detail_scope == "all":
            return True
        if detail_scope == "first_page":
            return page_idx == 1
        if detail_scope == "topN":
            if detail_top_n <= 0:
                return False
            # 避免 compare_report.html 的 page_idx=0 重复生成（page_0001.html 会覆盖 rank[0:topN]）
            if page_idx < 1:
                return False
            global_rank = (page_idx - 1) * page_size + row_offset_in_page
            return global_rank < detail_top_n
        return False

    def _render_rows_table(page_rows: List[Dict[str, str]], page_idx: int) -> str:
        """渲染单页的路径表，并按策略生成详情页。"""
        rows_paths: List[str] = []
        has_detail_points = bool(
            (golden_launch_by_path_id and test_launch_by_path_id)
            or (golden_capture_by_path_id and test_capture_by_path_id)
        )
        nonlocal generated_detail_count

        for row_offset, row in enumerate(page_rows):
            pid = (row.get("path_id") or "").strip()
            pid_t = (row.get("path_id_test") or pid).strip()
            pid_cell = html_module.escape(pid)
            if pid:
                fname = _detailFileName(row)
                if has_detail_points and _row_should_generate_detail(page_idx, row_offset):
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
                    generated_detail_count += 1
                # 即使不生成详情页，也保留链接（用户可后续用同参数重跑生成）
                pid_cell = f"<a href='../paths/{fname}' target='_blank'>{html_module.escape(pid)}</a>" if page_idx != 0 else f"<a href='paths/{fname}' target='_blank'>{html_module.escape(pid)}</a>"

            rows_paths.append(
                "<tr>"
                f"<td>{pid_cell}</td>"
                f"<td>{html_module.escape(_fmt_plain(row.get('startpoint')))}</td>"
                f"<td>{html_module.escape(_fmt_plain(row.get('endpoint')))}</td>"
                f"<td>{html_module.escape(_fmt_plain(row.get('slack_diff')))}</td>"
                f"<td>{html_module.escape(_fmt_plain(row.get('data_path_delay_diff')))}</td>"
                f"<td>{html_module.escape(_fmt_plain(row.get('launch_clock_delay_diff')))}</td>"
                f"<td>{html_module.escape(_fmt_plain(row.get('clock_uncertainty_diff')))}</td>"
                f"<td>{html_module.escape(_fmt_plain(row.get('clock_reconvergence_pessimism_diff')))}</td>"
                f"<td>{html_module.escape(_fmt_plain(row.get('data_path_point_count_diff')))}</td>"
                f"<td>{html_module.escape(_fmt_plain(row.get('launch_clock_point_count_diff')))}</td>"
                f"<td>{html_module.escape(_fmt_plain(row.get('capture_point_count_diff')))}</td>"
                "</tr>"
            )
        return (
            "<table>"
            "<tr>"
            "<th>path_id</th><th>startpoint</th><th>endpoint</th>"
            "<th>slack_diff</th>"
            "<th>data_path_delay_diff</th><th>launch_clock_delay_diff</th>"
            "<th>clock_uncertainty_diff</th><th>CRP_diff</th>"
            "<th>data_path_point_count_diff</th><th>launch_clock_point_count_diff</th><th>capture_point_count_diff</th>"
            "</tr>"
            + "".join(rows_paths)
            + "</table>"
        )

    # 写分页页（包含路径表 + 导航）
    for page_idx in range(1, max(total_pages, 1) + 1):
        start = (page_idx - 1) * page_size
        end = min(page_idx * page_size, len(sorted_rows))
        page_rows = sorted_rows[start:end]
        nav = _render_nav_links(page_idx, total_pages)
        table_html = _render_rows_table(page_rows, page_idx=page_idx)
        page_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>compare_path_summary 路径列表 - page {page_idx}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 20px; }}
    table {{ border-collapse: collapse; width: 100%; margin-bottom: 18px; }}
    th, td {{ border: 1px solid #ccc; padding: 6px 8px; font-size: 13px; }}
    th {{ background: #f3f3f3; text-align: left; }}
  </style>
</head>
<body>
  <h1>路径列表（关键差异，按 {html_module.escape(sort_by)} {'绝对值' if sort_abs else ''}排序）</h1>
  <p><a href="../compare_report.html">返回汇总首页</a></p>
  {nav}
  <div style="margin:12px 0;">
    <label for="sortBySelect">排序字段：</label>
    <select id="sortBySelect">{sort_options_html}</select>
    <label style="margin-left:14px;">
      <input type="checkbox" id="sortAbsChk" {'checked' if sort_abs else ''} /> abs
    </label>
  </div>
  <div id="table-container">{table_html}</div>
  <script src="../compare_rows_data.js"></script>
  <script>
    window.__compare_sort_page_idx = {page_idx - 1};
    window.__compare_sort_page_size = {page_size};
    window.__compare_sort_default_sort_by = {json.dumps(sort_by)};
    window.__compare_sort_default_sort_abs = {str(bool(sort_abs)).lower()};
    window.__compare_sort_detail_prefix = "../paths/";
  </script>
  <script src="../compare_sort_ui.js"></script>
  {nav}
</body>
</html>
"""
        with open(pages_dir / f"page_{page_idx:04d}.html", "w", encoding="utf-8") as f:
            f.write(page_html)

    # 首页只显示第一页的表格（更快）
    first_page_table = _render_rows_table(sorted_rows[:page_size], page_idx=0)
    first_nav = _render_nav_links(1, total_pages).replace("page_", "pages/page_")

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

  <h2>Slack PASS/FAIL 统计</h2>
  <table>
    <tr><th>PASS</th><th>FAIL</th><th>PASS ratio</th><th>Unknown</th></tr>
    <tr>
      <td>{html_module.escape(str(stats.get('slack_pass_stats', {}).get('pass_count', 0)))}</td>
      <td>{html_module.escape(str(stats.get('slack_pass_stats', {}).get('fail_count', 0)))}</td>
      <td>{html_module.escape(f"{float(stats.get('slack_pass_stats', {}).get('pass_ratio', 0.0)) * 100.0:.2f}%")}</td>
      <td>{html_module.escape(str(stats.get('slack_pass_stats', {}).get('unknown_count', 0)))}</td>
    </tr>
  </table>

  <h2>统计摘要（关键列）</h2>
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
  <p><b>分页：</b>每页 {page_size} 条；排序字段：{html_module.escape(sort_by)}（{'abs' if sort_abs else 'raw'}）。</p>
  <p>更多路径见：<a href="pages/page_0001.html">pages/page_0001.html</a></p>
  {first_nav}
  <div style="margin:12px 0;">
    <label for="sortBySelect">排序字段：</label>
    <select id="sortBySelect">{sort_options_html}</select>
    <label style="margin-left:14px;">
      <input type="checkbox" id="sortAbsChk" {'checked' if sort_abs else ''} /> abs
    </label>
  </div>
  <div id="table-container">{first_page_table}</div>
  <script src="compare_rows_data.js"></script>
  <script>
    window.__compare_sort_page_idx = 0;
    window.__compare_sort_page_size = {page_size};
    window.__compare_sort_default_sort_by = {json.dumps(sort_by)};
    window.__compare_sort_default_sort_abs = {str(bool(sort_abs)).lower()};
    window.__compare_sort_detail_prefix = "paths/";
  </script>
  <script src="compare_sort_ui.js"></script>

  <h2>图表</h2>
  {''.join(chart_tags) if chart_tags else '<p>未生成图表。</p>'}
</body>
</html>
"""
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    log_util.brief(
        f"[compare] detail pages generated: {generated_detail_count} "
        f"(detail_scope={detail_scope}, detail_top_n={detail_top_n})"
    )

