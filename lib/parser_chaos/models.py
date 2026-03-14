"""
parser_chaos 数据模型。

定义解析流水线产出的数据结构：ParseOutput 为单次抽取的完整结果容器，
包含按 path 合并后的 launch/capture/summary 以及按 startpoint 拆分后的 launch_clock/data_path。
与 lib.parsers 完全独立，不引用其任何代码。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ParseOutput:
    """
    解析结果容器，用于汇总多条 Timing Path 的解析结果。

    属性说明：
    - launch_rows: 所有 path 的 launch 段点表行（含 path_type 前为原始合并）
    - capture_rows: 所有 path 的 capture 段点表行
    - summary_rows: 每条 path 一行，含 path_id、startpoint、endpoint、slack、各段点数与延迟等
    - launch_clock_rows: launch 段中按 startpoint 拆分出的「launch clock」部分
    - data_path_rows: launch 段中按 startpoint 拆分出的「data path」部分
    """

    launch_rows: list[dict[str, Any]]
    capture_rows: list[dict[str, Any]]
    summary_rows: list[dict[str, Any]]
    launch_clock_rows: list[dict[str, Any]]
    data_path_rows: list[dict[str, Any]]
