"""
parser_chaos 结果聚合：按 path_id 排序后与 extract 相同的 launch_clock / data_path 拆分逻辑。
"""
from __future__ import annotations

from typing import Any

from lib.parser_V2.time_parser_base import TimeParser

from .constants import RESULT_SENTINEL
from .models import ParseOutput


def splitLaunchByCommonPin(
    launch_rows: list[dict[str, Any]],
    startpoint: str,
    delay_attr: str = "Incr",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int, int, float, float]:
    """委托 TimeParser，与 extract 单进程路径一致。"""
    return TimeParser.splitLaunchByCommonPin(launch_rows, startpoint, delay_attr=delay_attr)


def aggregateResults(
    results: list[tuple[int, dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]],
    delay_attr: str = "Incr",
) -> ParseOutput:
    """将多条单 path 结果聚合为 ParseOutput。"""
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
        meta["launch_clock_delay"] = TimeParser._cleanMetricFloat(lc_delay)
        meta["data_path_delay"] = TimeParser._cleanMetricFloat(dp_delay)
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
    return item == RESULT_SENTINEL
