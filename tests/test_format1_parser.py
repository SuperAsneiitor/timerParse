# -*- coding: utf-8 -*-
"""Format1(APR) 解析器测试：clock 行匹配（非固定 CPU_CLK）与 edge-triggered 变体。"""
from __future__ import annotations

import os
import tempfile
import unittest

import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.parser.format1_parser import Format1Parser
from lib.report_gen.format1 import Format1Report

_F1_TABLE_COLS = ["Point", "Fanout", "Derate", "Cap", "Trans", "Location", "Incr", "Path"]
_F1_WIDTHS = Format1Report().default_column_widths(_F1_TABLE_COLS)
_F1_SEP = "-" * max(80, 2 + sum(_F1_WIDTHS[c] for c in _F1_TABLE_COLS))

_F1_LVF_COLS = [
    "Point",
    "Fanout",
    "Derate",
    "Cap",
    "DTrans",
    "TransMean",
    "TransSensit",
    "TransValue",
    "Location",
    "Delta",
    "IncrMean",
    "IncrSensit",
    "IncrValue",
    "PathMean",
    "PathSensit",
    "PathValue",
]
_F1_LVF_WIDTHS = {
    "Point": 140,
    "Fanout": 8,
    "Derate": 14,
    "Cap": 10,
    "DTrans": 10,
    "TransMean": 9,
    "TransSensit": 9,
    "TransValue": 9,
    "Location": 24,
    "Delta": 9,
    "IncrMean": 9,
    "IncrSensit": 9,
    "IncrValue": 9,
    "PathMean": 9,
    "PathSensit": 9,
    "PathValue": 9,
}
_F1_LVF_SEP = "-" * max(80, 2 + sum(_F1_LVF_WIDTHS[c] for c in _F1_LVF_COLS))


def _f1_row(*cells: str) -> str:
    """与 format1 生成器列宽一致的表格行（两空格前缀 + 固定列宽）。"""
    parts = ["  "]
    for i, col in enumerate(_F1_TABLE_COLS):
        w = int(_F1_WIDTHS[col])
        text = cells[i] if i < len(cells) else ""
        parts.append(str(text).ljust(w)[:w])
    return "".join(parts).rstrip()


def _f1_header_line() -> str:
    return _f1_row(*_F1_TABLE_COLS)


def _f1_lvf_row(*cells: str) -> str:
    """构造 LVF 双层表头 / 数据行。"""
    parts = ["  "]
    for i, col in enumerate(_F1_LVF_COLS):
        w = int(_F1_LVF_WIDTHS[col])
        text = cells[i] if i < len(cells) else ""
        parts.append(str(text).ljust(w)[:w])
    return "".join(parts).rstrip()


def _f1_lvf_header_line() -> str:
    # 正确 LVF 分组表头：Trans/Incr/Path 在上一行（常带 - 装饰）
    return _f1_lvf_row(
        "",
        "",
        "",
        "",
        "",
        "-Trans-",
        "",
        "",
        "",
        "",
        "-Incr-",
        "",
        "",
        "-Path-",
        "",
        "",
    )


def _f1_lvf_sub_header_line() -> str:
    # 正确 LVF 属性表头：其他属性在下一行
    return _f1_lvf_row(
        "Point",
        "Fanout",
        "Derate",
        "Cap",
        "DTrans",
        "Mean",
        "Sensit",
        "Value",
        "Location",
        "Delta",
        "Mean",
        "Sensit",
        "Value",
        "Mean",
        "Sensit",
        "Value",
    )


def _format1_report_template(
    *,
    sp: str,
    ep: str,
    sp_edge: str,
    ep_edge: str,
    sp_clk: str,
    ep_clk: str,
    launch_clk: str,
    launch_edge: str,
    capture_clk: str,
    capture_edge: str,
) -> str:
    hdr = _f1_header_line()
    return rf"""
sta.timing_check_type: setup
  Startpoint: {sp} ({sp_edge} edge-triggered flip-flop clocked by {sp_clk})
  Endpoint: {ep} ({ep_edge} edge-triggered flip-flop clocked by {ep_clk})
  Scenario: demo

{hdr}
{_F1_SEP}
{_f1_row(f"clock {launch_clk} ({launch_edge} edge)", "", "", "", "", "", "0.0000", "0.0000")}
{_f1_row("U0/A (BUF)", "1", "0.9000", "0.0010", "0.0100", "(1.00, 2.00)", "0.1000", "0.1000 r")}
{_f1_row("data arrival time", "", "", "", "", "", "", "0.5750")}

{_f1_row(f"clock {capture_clk} ({capture_edge} edge)", "", "", "", "", "", "0.0000", "0.0000")}
{_f1_row("U1/Z (BUF)", "1", "0.9500", "0.0010", "0.0100", "(3.00, 4.00)", "0.2000", "0.7750 f")}
{_f1_row("library setup time", "", "", "", "", "", "-0.0190", "-0.0190")}
{_f1_row("data required time", "", "", "", "", "", "", "0.8000")}
{_f1_row("slack (MET)", "", "", "", "", "", "", "0.2250")}
"""


def _format1_capture_clock_no_edge() -> str:
    hdr = _f1_header_line()
    return rf"""
sta.timing_check_type: setup
  Startpoint: SP/Q (falling edge-triggered flip-flop clocked by CORECLK)
  Endpoint: EP/D (rising edge-triggered flip-flop clocked by CORECLK)
  Scenario: demo

{hdr}
{_F1_SEP}
{_f1_row("clock LAUNCH_CLK (rise edge)", "", "", "", "", "", "0.0000", "0.0000")}
{_f1_row("U0/A (BUF)", "1", "0.9000", "0.0010", "0.0100", "(1.00, 2.00)", "0.1000", "0.1000 r")}
{_f1_row("data arrival time", "", "", "", "", "", "", "0.5750")}

{_f1_row("clock CAPTURE_CLK", "", "", "", "", "", "0.0000", "0.0000")}
{_f1_row("clock network delay (propagated)", "", "", "", "", "", "0.0000", "0.0000")}
{_f1_row("U1/Z (BUF)", "1", "0.9500", "0.0010", "0.0100", "(3.00, 4.00)", "0.2000", "0.7750 r")}
{_f1_row("library setup time", "", "", "", "", "", "-0.0190", "-0.0190")}
{_f1_row("data required time", "", "", "", "", "", "", "0.8000")}
{_f1_row("slack (MET)", "", "", "", "", "", "", "0.2250")}
"""


class TestFormat1ClockRegex(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = Format1Parser()

    def _parse_text(self, text: str):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".rpt", delete=False, encoding="utf-8") as f:
            f.write(text.lstrip("\n"))
            path = f.name
        try:
            return self.parser.parseReport(path)
        finally:
            os.unlink(path)

    def test_clock_line_matches_any_clock_name(self):
        """点表 clock 行不应硬编码 CPU_CLK，应能匹配任意 clock 名。"""
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
        out = self._parse_text(rpt)
        self.assertGreater(len(out.launch_rows), 0)
        self.assertGreater(len(out.capture_rows), 0)
        # launch 第一行通常为 clock 行
        self.assertIn("clock", out.launch_rows[0]["point"])
        self.assertIn("CORE_CLK", out.launch_rows[0]["point"])
        # capture 第一行通常为 clock 行
        self.assertIn("clock", out.capture_rows[0]["point"])
        self.assertIn("ANOTHER_CLK", out.capture_rows[0]["point"])

    def test_clock_line_matches_fall_edge(self):
        """点表 clock 行应支持 (fall edge)。"""
        rpt = _format1_report_template(
            sp="SP/Q",
            ep="EP/D",
            sp_edge="falling",
            ep_edge="rising",
            sp_clk="CLK_F",
            ep_clk="CLK_F",
            launch_clk="CLK_F",
            launch_edge="fall",
            capture_clk="CLK_F",
            capture_edge="fall",
        )
        out = self._parse_text(rpt)
        self.assertGreater(len(out.launch_rows), 0)
        self.assertIn("(fall edge)", out.launch_rows[0]["point"])

    def test_start_end_clocked_by_parses_various_edge_triggered_text(self):
        """Startpoint/Endpoint 中不仅 rising/falling，也可能出现 falling rising edge-triggered 文案。"""
        rpt = _format1_report_template(
            sp="SP/Q",
            ep="EP/D",
            sp_edge="falling rising",
            ep_edge="falling rising",
            sp_clk="MIXEDCLK",
            ep_clk="MIXEDCLK",
            launch_clk="MIXED_CLK",
            launch_edge="rise",
            capture_clk="MIXED_CLK",
            capture_edge="rise",
        )
        out = self._parse_text(rpt)
        self.assertEqual(out.summary_rows[0]["startpoint_clock"], "MIXEDCLK")
        self.assertEqual(out.summary_rows[0]["endpoint_clock"], "MIXEDCLK")

    def test_capture_clock_line_without_edge(self):
        """capture 段起始的 clock 行可能没有 (rise|fall edge)，仍应能识别为 capture 起点。"""
        out = self._parse_text(_format1_capture_clock_no_edge())
        self.assertGreater(len(out.capture_rows), 0)
        # capture 第一行应为 "clock CAPTURE_CLK" 而不是 "clock network delay ..."
        self.assertIn("clock", out.capture_rows[0]["point"])
        self.assertIn("CAPTURE_CLK", out.capture_rows[0]["point"])
        self.assertNotIn("network delay", out.capture_rows[0]["point"])

    def test_trigger_edge_extracted_from_path_tail(self):
        """input/output pin 的 Path 末尾 r/f 应写入 trigger_edge，并从 Path 中移除。"""
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
        out = self._parse_text(rpt)
        launch_pin = next((r for r in out.launch_rows if "U0/A" in r.get("point", "")), None)
        capture_pin = next((r for r in out.capture_rows if "U1/Z" in r.get("point", "")), None)
        self.assertIsNotNone(launch_pin)
        self.assertIsNotNone(capture_pin)
        self.assertEqual(launch_pin.get("trigger_edge"), "r")
        self.assertEqual(capture_pin.get("trigger_edge"), "f")
        self.assertFalse(str(launch_pin.get("Path", "")).strip().endswith(" r"))
        self.assertFalse(str(capture_pin.get("Path", "")).strip().endswith(" f"))

    def test_derate_column_on_pin_rows(self):
        """Fanout 与 Cap 之间的 Derate 列应在 pin 行解析为四位小数文本。"""
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
        out = self._parse_text(rpt)
        launch_pin = next((r for r in out.launch_rows if "U0/A" in r.get("point", "")), None)
        capture_pin = next((r for r in out.capture_rows if "U1/Z" in r.get("point", "")), None)
        self.assertEqual((launch_pin or {}).get("Derate"), "0.9000")
        self.assertEqual((capture_pin or {}).get("Derate"), "0.9500")


class TestFormat1LvfParser(unittest.TestCase):
    """Format1 LVF 变体：三元组列、DTrans/Delta、双值 Derate。"""

    def setUp(self) -> None:
        self.parser = Format1Parser()

    def _parse_text(self, text: str):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".rpt", delete=False, encoding="utf-8") as f:
            f.write(text.lstrip("\n"))
            path = f.name
        try:
            return self.parser.parseReport(path)
        finally:
            os.unlink(path)

    def test_lvf_rows_parse_new_columns_and_compatibility_values(self):
        rpt = rf"""
sta.timing_check_type: setup
  Startpoint: SP/Q (falling edge-triggered flip-flop clocked by CORECLK)
  Endpoint: EP/D (rising edge-triggered flip-flop clocked by CORECLK)
  Scenario: demo

{_f1_lvf_header_line()}
{_f1_lvf_sub_header_line()}
{_F1_LVF_SEP}
{_f1_lvf_row("clock CORECLK (rise edge)", "", "", "", "", "", "", "", "", "", "", "", "0.0450", "", "", "0.1460")}
{_f1_lvf_row("U0/A (BUF)", "1", "0.8766:1.1000", "0.0080", "0.0000", "0.0450", "0.000", "0.0450", "(522.4000, 695.8100)", "0.0000", "0.0450", "0.000", "0.0450", "0.1460", "0.0260", "0.1460 r")}
{_f1_lvf_row("data arrival time", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "0.5750")}

{_f1_lvf_row("clock CORECLK (rise edge)", "", "", "", "", "", "", "", "", "", "", "", "0.0190", "", "", "0.0190")}
{_f1_lvf_row("U1/Z (BUF)", "1", "0.8000:0.9000", "0.0040", "0.0000", "0.0420", "0.000", "0.0420", "(237.7400, 833.8600)", "0.0000", "0.0450", "0.000", "0.0450", "0.1930", "0.0470", "0.1930 f")}
{_f1_lvf_row("library setup time", "", "", "", "", "", "", "", "", "", "", "", "-0.0190", "", "", "-0.0190")}
{_f1_lvf_row("data required time", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "0.8000")}
{_f1_lvf_row("slack (MET)", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "0.2250")}
"""
        out = self._parse_text(rpt)
        launch_pin = next((r for r in out.launch_rows if "U0/A" in r.get("point", "")), None)
        capture_pin = next((r for r in out.capture_rows if "U1/Z" in r.get("point", "")), None)
        self.assertIsNotNone(launch_pin)
        self.assertIsNotNone(capture_pin)

        self.assertEqual((launch_pin or {}).get("Derate"), "0.8766:1.1000")
        self.assertEqual((launch_pin or {}).get("DerateA"), "0.8766")
        self.assertEqual((launch_pin or {}).get("DerateB"), "1.1000")
        self.assertEqual((launch_pin or {}).get("D-Trans"), "0.0000")
        self.assertEqual((launch_pin or {}).get("Delta"), "0.0000")
        self.assertEqual((launch_pin or {}).get("TransMean"), "0.0450")
        self.assertEqual((launch_pin or {}).get("TransSensit"), "0.000")
        self.assertEqual((launch_pin or {}).get("TransValue"), "0.0450")
        self.assertEqual((launch_pin or {}).get("IncrMean"), "0.0450")
        self.assertEqual((launch_pin or {}).get("IncrSensit"), "0.000")
        self.assertEqual((launch_pin or {}).get("IncrValue"), "0.0450")
        self.assertEqual((launch_pin or {}).get("PathMean"), "0.1460")
        self.assertEqual((launch_pin or {}).get("PathSensit"), "0.0260")
        self.assertEqual((launch_pin or {}).get("PathValue"), "0.1460")
        self.assertEqual((launch_pin or {}).get("Trans"), "0.0450")
        self.assertEqual((launch_pin or {}).get("Incr"), "0.0450")
        self.assertEqual((launch_pin or {}).get("Path"), "0.1460")
        self.assertEqual((launch_pin or {}).get("trigger_edge"), "r")

        self.assertEqual((capture_pin or {}).get("DerateA"), "0.8000")
        self.assertEqual((capture_pin or {}).get("DerateB"), "0.9000")
        self.assertEqual((capture_pin or {}).get("PathValue"), "0.1930")
        self.assertEqual((capture_pin or {}).get("trigger_edge"), "f")

        launch_clock = out.launch_rows[0]
        self.assertEqual((launch_clock.get("IncrValue") or "").strip(), "0.0450")
        self.assertEqual((launch_clock.get("PathValue") or "").strip(), "0.1460")

    def test_lvf_rows_parse_without_fixed_column_alignment(self):
        """LVF 行即使列宽不对齐（仅用 2+ 空格分隔）也应解析出关键字段。"""
        rpt = """
sta.timing_check_type: setup
  Startpoint: SP/Q (falling edge-triggered flip-flop clocked by CORECLK)
  Endpoint: EP/D (rising edge-triggered flip-flop clocked by CORECLK)
  Scenario: demo

  Point  Fanout  Derate  Cap  DTrans  -Trans-  -Incr-  -Path-
  Point  Fanout  Derate  Cap  DTrans  Mean  Sensit  Value  Location  Delta  Mean  Sensit  Value  Mean  Sensit  Value
  ------------------------------------------------------------------------------------------------------------------------
  clock CORECLK (rise edge)  0.0450  0.1460
  U0/A (BUF)  1  0.8766:1.1000  0.0080  0.0000  0.0450  0.000  0.0450  (522.4, 695.8)  0.0000  0.0450  0.000  0.0450  0.1460  0.0260  0.1460 r
  data arrival time  0.5750

  clock CORECLK (rise edge)  0.0190  0.0190
  U1/Z (BUF)  1  0.8000:0.9000  0.0040  0.0000  0.0420  0.000  0.0420  (237.7, 833.8)  0.0000  0.0450  0.000  0.0450  0.1930  0.0470  0.1930 f
  library setup time  -0.0190  -0.0190
  data required time  0.8000
  slack (MET)  0.2250
"""
        out = self._parse_text(rpt)
        launch_pin = next((r for r in out.launch_rows if "U0/A" in r.get("point", "")), None)
        self.assertIsNotNone(launch_pin)
        self.assertEqual((launch_pin or {}).get("TransMean"), "0.0450")
        self.assertEqual((launch_pin or {}).get("IncrValue"), "0.0450")
        self.assertEqual((launch_pin or {}).get("PathValue"), "0.1460")
        self.assertEqual((launch_pin or {}).get("trigger_edge"), "r")


if __name__ == "__main__":
    unittest.main()
