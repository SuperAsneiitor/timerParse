"""
parser_chaos：多进程 + 队列的高吞吐抽取流水线。

与 extract 共用 parser_V2 解析器与 CSV schema；差异在于 1 个分割器进程与 N 个 Worker 并行解析。
"""
from __future__ import annotations

from .constants import FORMAT1, FORMAT_FORMAT2, FORMAT_PT
from .models import ParseOutput
from .run import detectFormatFromReport, runExtractChaos

__all__ = [
    "runExtractChaos",
    "detectFormatFromReport",
    "ParseOutput",
    "FORMAT1",
    "FORMAT_FORMAT2",
    "FORMAT_PT",
]
