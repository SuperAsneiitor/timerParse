"""lib.parser：唯一解析实现包（布局解析 + 完整 extract 解析器）。"""
from .engine import TimingParserV2, create_timing_report_parser, detect_report_format
from .format1_parser import Format1Parser
from .format2_parser import Format2Parser
from .models import ParseResult, PathRecord, PointRecord
from .parallel_extract import (
    FORMAT1,
    FORMAT_FORMAT2,
    FORMAT_PT,
    detectFormatFromReport,
    runExtractChaos,
    runExtractParallel,
)
from .pt_parser import PtParser
from .time_parser_base import ParseOutput, TimeParser

__all__ = [
    "TimingParserV2",
    "create_timing_report_parser",
    "detect_report_format",
    "ParseResult",
    "PathRecord",
    "PointRecord",
    "ParseOutput",
    "TimeParser",
    "Format1Parser",
    "Format2Parser",
    "PtParser",
    "FORMAT1",
    "FORMAT_FORMAT2",
    "FORMAT_PT",
    "runExtractParallel",
    "runExtractChaos",
    "detectFormatFromReport",
]
