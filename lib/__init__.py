from __future__ import annotations

from .format1_parser import Format1Parser
from .format2_parser import Format2Parser
from .pt_parser import PtParser
from .time_parser_base import ParseOutput, TimeParser


def detect_report_format(peek_text: str) -> str:
    """根据报告开头文本自动识别格式。"""
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


def create_parser(format_key: str) -> TimeParser:
    """按格式创建解析器实例。"""
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
    "create_parser",
    "detect_report_format",
]
