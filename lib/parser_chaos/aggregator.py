"""
parser_chaos 结果聚合。

负责将各 worker 返回的单 path 解析结果按 path_id 排序后，对每条 path 的 launch 段
按 startpoint 拆分为 launch_clock 与 data_path，并合并为最终 ParseOutput。
与 lib.parsers 完全独立。
"""
from __future__ import annotations

from typing import Any

from .constants import RESULT_SENTINEL
from .models import ParseOutput
from .utils import cleanMetricFloat, normalizePin, sumDelayInRows

def splitLaunchByCommonPin(
    launch_rows: list[dict[str, Any]],
    startpoint: str,
    delay_attr: str = "Incr",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int, int, float, float]:
    """
    按 startpoint 将 launch 段拆为 launch_clock 与 data_path。

    逻辑：遍历 launch_rows，若当前行的 point 归一化后等于 startpoint，或是 startpoint
    下挂的任一具体 pin（如 startpoint/Q），则该行及之后归入 data_path，之前归入 launch_clock；
    并为每行设置 path_type。返回 (launch_clock_rows, data_path_rows, lc_count, dp_count, lc_delay, dp_delay)。
    """
    target = normalizePin(startpoint)
    launch_clock: list[dict[str, Any]] = []
    data_path: list[dict[str, Any]] = []
    found = False
    for row in launch_rows:
        pt = (row.get("point") or "").strip()
        norm_pt = normalizePin(pt)
        is_target_row = norm_pt == target or (target and norm_pt.startswith(target + "/"))
        if not found and is_target_row:
            found = True
            row["path_type"] = "data_path"
            data_path.append(row)
            continue
        if not found:
            row["path_type"] = "launch_clock"
            launch_clock.append(row)
        else:
            row["path_type"] = "data_path"
            data_path.append(row)
    lc_delay = sumDelayInRows(launch_clock, delay_attr)
    dp_delay = sumDelayInRows(data_path, delay_attr)
    return launch_clock, data_path, len(launch_clock), len(data_path), lc_delay, dp_delay


def aggregateResults(
    results: list[tuple[int, dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]],
    delay_attr: str = "Incr",
) -> ParseOutput:
    """
    将多条 (path_id, meta, launch_rows, capture_rows) 聚合为单一 ParseOutput。

    逻辑：按 path_id 排序后，对每条 path 的 launch 调用 splitLaunchByCommonPin，
    将 meta 补全 launch_clock_point_count、data_path_point_count、capture_point_count、
    launch_clock_delay、data_path_delay，再合并所有 launch/capture/summary/launch_clock/data_path。
    """
    results_sorted = sorted(results, key=lambda x: x[0])
    launch_rows: list[dict[str, Any]] = []
    capture_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    launch_clock_rows: list[dict[str, Any]] = []
    data_path_rows: list[dict[str, Any]] = []
    for _path_id, meta, launch, capture in results_sorted:
        lc, dp, lc_n, dp_n, lc_delay, dp_delay = splitLaunchByCommonPin(
            launch, meta.get("startpoint", ""), delay_attr=delay_attr
        )
        meta["launch_clock_point_count"] = lc_n
        meta["data_path_point_count"] = dp_n
        meta["capture_point_count"] = len(capture)
        meta["launch_clock_delay"] = cleanMetricFloat(lc_delay)
        meta["data_path_delay"] = cleanMetricFloat(dp_delay)
        summary_rows.append(meta)
        launch_rows.extend(launch)
        launch_clock_rows.extend(lc)
        data_path_rows.extend(dp)
        capture_rows.extend(capture)
    return ParseOutput(
        launch_rows=launch_rows,
        capture_rows=capture_rows,
        summary_rows=summary_rows,
        launch_clock_rows=launch_clock_rows,
        data_path_rows=data_path_rows,
    )


def isResultSentinel(item: tuple) -> bool:
    """判断 result_queue 取出的项是否为 worker 退出的哨兵。"""
    return item == RESULT_SENTINEL
