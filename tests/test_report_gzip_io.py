# -*- coding: utf-8 -*-
"""报告 .gz 透明读取：与明文 .rpt 分块及解析结果一致。"""
from __future__ import annotations

import gzip
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib.parser.format1_parser import Format1Parser
from lib.parser.format2_parser import Format2Parser
from lib.parser.parallel_extract import (
    FORMAT1,
    FORMAT_FORMAT2,
    detect_format_from_report_file,
    split_report_into_blocks,
)
from tests.test_format1_parser import _format1_report_template
from tests.test_format2_parser import MINIMAL_FORMAT2_REPORT


def _write_plain_and_gz(text: str, suffix: str) -> tuple[str, str]:
    """返回 (明文路径, 同内容 gzip 路径)。"""
    raw = text.lstrip("\n").encode("utf-8")
    d = tempfile.mkdtemp()
    plain = os.path.join(d, f"demo{suffix}")
    gz_path = os.path.join(d, f"demo{suffix}.gz")
    with open(plain, "wb") as f:
        f.write(raw)
    with gzip.open(gz_path, "wb") as f:
        f.write(raw)
    return plain, gz_path


def _cleanup_pair(plain: str, gz_path: str) -> None:
    d = os.path.dirname(plain)
    try:
        os.unlink(plain)
        os.unlink(gz_path)
        os.rmdir(d)
    except OSError:
        pass


class TestReportGzipIo(unittest.TestCase):
    def test_format1_scan_and_parse_matches_gzip(self) -> None:
        rpt = _format1_report_template(
            sp="SP/Q",
            ep="EP/D",
            sp_edge="falling",
            ep_edge="rising",
            sp_clk="CORECLK",
            ep_clk="CORECLK",
            launch_clk="CORE_CLK",
            launch_edge="rise",
            capture_clk="ANOTHER_CLK",
            capture_edge="rise",
        )
        plain, gz_path = _write_plain_and_gz(rpt, ".rpt")
        try:
            p = Format1Parser()
            b1 = p.scanPathBlocks(plain)
            b2 = p.scanPathBlocks(gz_path)
            self.assertEqual(b1, b2)
            o1 = p.parseReport(plain)
            o2 = p.parseReport(gz_path)
            self.assertEqual(len(o1.launch_rows), len(o2.launch_rows))
            self.assertEqual(len(o1.capture_rows), len(o2.capture_rows))
            self.assertEqual(len(o1.summary_rows), len(o2.summary_rows))
            self.assertEqual(o1.summary_rows, o2.summary_rows)
        finally:
            _cleanup_pair(plain, gz_path)

    def test_format2_scan_matches_gzip(self) -> None:
        plain, gz_path = _write_plain_and_gz(MINIMAL_FORMAT2_REPORT, ".rpt")
        try:
            p = Format2Parser()
            self.assertEqual(p.scanPathBlocks(plain), p.scanPathBlocks(gz_path))
            self.assertEqual(
                detect_format_from_report_file(plain),
                detect_format_from_report_file(gz_path),
            )
        finally:
            _cleanup_pair(plain, gz_path)

    def test_parallel_split_matches_gzip(self) -> None:
        rpt = _format1_report_template(
            sp="A",
            ep="B",
            sp_edge="rising",
            ep_edge="rising",
            sp_clk="C",
            ep_clk="C",
            launch_clk="C",
            launch_edge="rise",
            capture_clk="C",
            capture_edge="rise",
        )
        plain, gz_path = _write_plain_and_gz(rpt, ".rpt")
        try:
            self.assertEqual(
                split_report_into_blocks(plain, FORMAT1),
                split_report_into_blocks(gz_path, FORMAT1),
            )
        finally:
            _cleanup_pair(plain, gz_path)

    def test_detect_format2_from_gz(self) -> None:
        plain, gz_path = _write_plain_and_gz(MINIMAL_FORMAT2_REPORT, ".rpt")
        try:
            self.assertEqual(detect_format_from_report_file(gz_path), FORMAT_FORMAT2)
        finally:
            _cleanup_pair(plain, gz_path)


if __name__ == "__main__":
    unittest.main()
