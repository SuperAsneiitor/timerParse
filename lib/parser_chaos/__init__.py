"""
parser_chaos：基于「分割器进程 + 解析器 Worker 进程 + 队列」的 Timing 报告解析流水线。

与 lib.parsers 完全独立，不引用其任何代码。架构：1 个报告分割器进程负责读报告并切分 path 块放入
任务队列；N 个解析器 Worker 进程从队列取块、解析单条 path、将结果放入结果队列；主进程收集结果后
聚合（按 startpoint 拆分 launch_clock/data_path）并写出 CSV。

主要入口：runExtractChaos(report_path, output_dir, format_key, num_workers)
格式检测：detectFormatFromReport(report_path)
"""

from __future__ import annotations

from .constants import FORMAT_APR, FORMAT_FORMAT1, FORMAT_FORMAT2, FORMAT_PT
from .models import ParseOutput
from .run import detectFormatFromReport, runExtractChaos

__all__ = [
    "runExtractChaos",
    "detectFormatFromReport",
    "ParseOutput",
    "FORMAT_FORMAT1",
    "FORMAT_FORMAT2",
    "FORMAT_PT",
    "FORMAT_APR",
]
