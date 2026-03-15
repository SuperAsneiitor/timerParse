"""
parser_chaos 常量与配置。

集中定义格式键名、抽取结果中保留的语义列顺序、以及各格式默认列配置。
与 lib.parsers 完全独立。
"""
from __future__ import annotations

# 支持的报告格式键（与 CLI --format 一致）；apr 与 format1 为同一格式，入口处统一为 format1
FORMAT1 = "format1"
FORMAT_FORMAT2 = "format2"
FORMAT_PT = "pt"

# 抽取结果 CSV 中保留的语义列顺序（与格式无关的统一列集合）
SEMANTIC_POINT_ATTRS = [
    "Type",
    "Fanout",
    "Cap",
    "D-Trans",
    "Trans",
    "Derate",
    "Mean",
    "Sensit",
    "x-coord",
    "y-coord",
    "D-Delay",
    "Delay",
    "Incr",
    "Time",
    "Path",
    "trigger_edge",
    "Description",
]

# 点表 CSV 的公共列（每条点行都包含）
POINT_BASE_COLUMNS = [
    "path_id",
    "startpoint",
    "endpoint",
    "startpoint_clock",
    "endpoint_clock",
    "slack",
    "slack_status",
    "point_index",
    "point",
]

# path_summary 表列（每条 path 一行）
SUMMARY_COLUMNS = [
    "path_id",
    "startpoint",
    "endpoint",
    "arrival_time",
    "required_time",
    "slack",
    "launch_clock_point_count",
    "data_path_point_count",
    "capture_point_count",
    "launch_clock_delay",
    "data_path_delay",
]

# 任务队列结束哨兵：分割器放入后，worker 收到即退出
TASK_SENTINEL = (None, None)

# 结果队列结束哨兵：每个 worker 退出前放入一条，主进程据此统计已退出的 worker 数
RESULT_SENTINEL = (None, None, None, None)
