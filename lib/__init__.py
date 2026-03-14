"""
lib 包入口：报告格式检测、解析器工厂与对外导出。

职责：detectReportFormat 根据报告文本识别 format1/format2/pt；
createParser 按格式返回对应解析器实例。解析与抽取由 parsers 与 extract 完成。
"""
from __future__ import annotations

from .parsers.format1_parser import Format1Parser
from .parsers.format2_parser import Format2Parser
from .parsers.pt_parser import PtParser
from .parsers.time_parser_base import ParseOutput, TimeParser


def detectReportFormat(peek_text: str) -> str:
    """根据报告开头文本自动识别格式，返回 'format1' / 'format2' / 'pt'。"""
    if not peek_text:
        return "format1"
    if "Path Start" in peek_text and "Path End" in peek_text and (
        "slack (VIOLATED" in peek_text or "slack (MET)" in peek_text
    ):
        return "format2"
    if "Report : timing" in peek_text and "Derate" in peek_text and "Startpoint:" in peek_text:
        return "pt"
    if "Startpoint:" in peek_text and ("slack (VIOLATED" in peek_text or "slack (MET)" in peek_text):
        return "format1"
    return "format1"


def createParser(format_key: str) -> TimeParser:
    """按格式键（format1/format2/pt/apr）创建对应解析器实例。"""
    key = (format_key or "").strip().lower()
    if key in ("format1", "apr"):
        return Format1Parser()
    if key == "format2":
        return Format2Parser()
    if key == "pt":
        return PtParser()
    raise ValueError(f"Unsupported format: {format_key}")


__all__ = [
    "ParseOutput",
    "TimeParser",
    "Format1Parser",
    "Format2Parser",
    "PtParser",
    "createParser",
    "detectReportFormat",
]
