"""lib.parser 解析引擎。

- TimingParserV2：基于 YAML 布局的轻量结构化解析（parse_text → ParseResult）。
- create_timing_report_parser：与 lake extract / gen-pt / 对比流水线对齐的完整解析器（TimeParser）。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from .classifier import classify_line
from .extractor import extract_attrs_by_type
from .layout_loader import load_layout
from .models import ParseResult, PathRecord, PointRecord

if TYPE_CHECKING:
    from .time_parser_base import ParseOutput, TimeParser


class TimingParserV2:
    """Timing 解析统一入口：布局模式 parse_text；完整模式 parse_report_for_extract。"""

    def __init__(self, format_name: str) -> None:
        self.format_name = (format_name or "").strip().lower()
        self.layout = load_layout(self.format_name)

    def parse_report_for_extract(self, report_path: str | Path) -> "ParseOutput":
        """完整列宽解析，产出与 extract 子命令相同的 ParseOutput（format 不可为 auto）。"""
        impl = create_timing_report_parser(self.format_name)
        return impl.parseReport(str(report_path))

    def parse_file(self, report_path: str | Path) -> ParseResult:
        text = Path(report_path).read_text(encoding="utf-8", errors="ignore")
        return self.parse_text(text)

    def parse_text(self, report_text: str) -> ParseResult:
        lines = report_text.splitlines()
        path_ranges = self._split_path_ranges(lines)
        result = ParseResult(format_name=self.format_name)
        for i, (start, end) in enumerate(path_ranges, start=1):
            section = lines[start:end]
            result.paths.append(self._parse_one_path(i, section))
        return result

    def _split_path_ranges(self, lines: list[str]) -> list[tuple[int, int]]:
        start_re = re.compile(str(self.layout.get("path_start_regex") or r"^\s*Startpoint\s*:"))
        idx = [i for i, line in enumerate(lines) if start_re.search(line or "")]
        if not idx:
            return [(0, len(lines))] if lines else []
        ranges: list[tuple[int, int]] = []
        for n, s in enumerate(idx):
            e = idx[n + 1] if n + 1 < len(idx) else len(lines)
            ranges.append((s, e))
        return ranges

    def _parse_one_path(self, path_id: int, section: list[str]) -> PathRecord:
        rec = PathRecord(path_id=path_id)
        rec.meta = self._parse_meta(section)
        data_lines = self._extract_table_lines(section)
        rec.launch_points, rec.capture_points = self._parse_points(data_lines)
        return rec

    def _parse_meta(self, section: list[str]) -> dict[str, str]:
        meta: dict[str, str] = {}
        for key, pat in (self.layout.get("meta_regex") or {}).items():
            reg = re.compile(str(pat), re.IGNORECASE)
            for line in section:
                m = reg.search(line or "")
                if m:
                    if m.groups():
                        meta[str(key)] = m.group(1).strip()
                    else:
                        meta[str(key)] = line.strip()
                    break
        return meta

    def _extract_table_lines(self, section: list[str]) -> list[str]:
        header_words = [str(x).lower() for x in (self.layout.get("table_header_contains") or [])]
        separator_re = re.compile(str(self.layout.get("table_separator_regex") or r"^-{3,}\s*$"))
        begin = 0
        for i, line in enumerate(section):
            low = (line or "").lower()
            if header_words and all(x in low for x in header_words):
                begin = i + 1
                continue
            if i >= begin and separator_re.search(line or ""):
                begin = i + 1
                break
        return section[begin:]

    def _parse_points(self, lines: list[str]) -> tuple[list[PointRecord], list[PointRecord]]:
        rules = list(self.layout.get("type_classify") or [])
        arrival_re = re.compile(str(self.layout.get("arrival_switch_regex") or r"\bdata\s+arrival\s+time\b"), re.IGNORECASE)
        stop_res = [re.compile(str(p), re.IGNORECASE) for p in (self.layout.get("capture_stop_regexes") or [r"\bslack\b"])]
        launch: list[PointRecord] = []
        capture: list[PointRecord] = []
        phase = "launch"

        for raw in lines:
            line = (raw or "").strip()
            if not line:
                continue
            if arrival_re.search(line):
                phase = "capture"
                continue
            if any(r.search(line) for r in stop_res):
                break
            ptype = classify_line(line, rules, default_type="other")
            point, attrs = extract_attrs_by_type(line, ptype, self.layout)
            rec = PointRecord(point=point, point_type=ptype, attrs=attrs, raw_line=line)
            if phase == "launch":
                launch.append(rec)
            else:
                capture.append(rec)
        return launch, capture


def detect_report_format(peek_text: str) -> str:
    """根据报告开头文本自动识别 format1 / format2 / pt。"""
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


def create_timing_report_parser(format_key: str) -> "TimeParser":
    """创建与 extract 输出 schema 一致的解析器实例。"""
    key = (format_key or "").strip().lower()
    if key in ("format1", "apr"):
        from .format1_parser import Format1Parser

        return Format1Parser()
    if key == "format2":
        from .format2_parser import Format2Parser

        return Format2Parser()
    if key == "pt":
        from .pt_parser import PtParser

        return PtParser()
    raise ValueError(f"Unsupported format: {format_key}")
