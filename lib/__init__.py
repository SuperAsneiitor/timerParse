"""
lib 包入口（模块分工）：

- parser_V2/   Timing 解析唯一实现：TimeParser 子类 + YAML 布局引擎 TimingParserV2
- extract.py   主抽取：单进程或多进程 Pool → 标准 CSV
- parser_chaos/  高吞吐：分割器 + 队列 + Worker（解析器与 extract 相同）
- report_gen/  按 YAML 生成报告；compare*/ gen_pt_report_timing / cli / log_util 为下游工具
"""
from __future__ import annotations

from .parser_V2.engine import create_timing_report_parser, detect_report_format
from .parser_V2.format1_parser import Format1Parser
from .parser_V2.format2_parser import Format2Parser
from .parser_V2.pt_parser import PtParser
from .parser_V2.time_parser_base import ParseOutput, TimeParser


def detectReportFormat(peek_text: str) -> str:
    """根据报告开头文本自动识别格式，返回 'format1' / 'format2' / 'pt'。"""
    return detect_report_format(peek_text)


def createParser(format_key: str) -> TimeParser:
    """按格式键创建解析器（与 create_timing_report_parser 等价）。"""
    return create_timing_report_parser(format_key)


__all__ = [
    "ParseOutput",
    "TimeParser",
    "Format1Parser",
    "Format2Parser",
    "PtParser",
    "createParser",
    "create_timing_report_parser",
    "detectReportFormat",
    "detect_report_format",
]
