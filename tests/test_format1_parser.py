# -*- coding: utf-8 -*-
"""Format1(APR) 解析器测试：clock 行匹配（非固定 CPU_CLK）与 edge-triggered 变体。"""
from __future__ import annotations

import os
import tempfile
import unittest

import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.format1_parser import Format1Parser


FORMAT1_REPORT_TEMPLATE = r"""
sta.timing_check_type: setup
  Startpoint: {sp} ({sp_edge} edge-triggered flip-flop clocked by {sp_clk})
  Endpoint: {ep} ({ep_edge} edge-triggered flip-flop clocked by {ep_clk})
  Scenario: demo

  Point                                                                                                                                                                    Fanout  Cap         Trans       Location           Incr        Path
  ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  clock {launch_clk} ({launch_edge} edge)                                                                                                                                                                                                   0.000       0.000
  U0/A (BUF)                                                                                                                                                                      1       0.001       0.010       (1.0, 2.0)        0.100       0.100 r
  data arrival time                                                                                                                                                                                                                       0.575

  clock {capture_clk} ({capture_edge} edge)                                                                                                                                                                                                  0.000       0.000
  U1/Z (BUF)                                                                                                                                                                      1       0.001       0.010       (3.0, 4.0)        0.200       0.775 f
  library setup time                                                                                                                                                                                                         -0.019      -0.019
  data required time                                                                                                                                                                                                                      0.800
  slack (MET)                                                                                                                                                                                                                             0.225
"""


FORMAT1_CAPTURE_CLOCK_NO_EDGE = r"""
sta.timing_check_type: setup
  Startpoint: SP/Q (falling edge-triggered flip-flop clocked by CORECLK)
  Endpoint: EP/D (rising edge-triggered flip-flop clocked by CORECLK)
  Scenario: demo

  Point                                                                                                                                                                    Fanout  Cap         Trans       Location           Incr        Path
  ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  clock LAUNCH_CLK (rise edge)                                                                                                                                                                                                   0.000       0.000
  U0/A (BUF)                                                                                                                                                                      1       0.001       0.010       (1.0, 2.0)        0.100       0.100 r
  data arrival time                                                                                                                                                                                                                       0.575

  clock CAPTURE_CLK                                                                                                                                                                                                                          0.000       0.000
  clock network delay (propagated)                                                                                                                                                                                            0.000       0.000
  U1/Z (BUF)                                                                                                                                                                      1       0.001       0.010       (3.0, 4.0)        0.200       0.775 r
  library setup time                                                                                                                                                                                                         -0.019      -0.019
  data required time                                                                                                                                                                                                                      0.800
  slack (MET)                                                                                                                                                                                                                             0.225
"""


class TestFormat1ClockRegex(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = Format1Parser()

    def _parse_text(self, text: str):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".rpt", delete=False, encoding="utf-8") as f:
            f.write(text.lstrip("\n"))
            path = f.name
        try:
            return self.parser.parse_report(path)
        finally:
            os.unlink(path)

    def test_clock_line_matches_any_clock_name(self):
        """点表 clock 行不应硬编码 CPU_CLK，应能匹配任意 clock 名。"""
        rpt = FORMAT1_REPORT_TEMPLATE.format(
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
        rpt = FORMAT1_REPORT_TEMPLATE.format(
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
        rpt = FORMAT1_REPORT_TEMPLATE.format(
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
        out = self._parse_text(FORMAT1_CAPTURE_CLOCK_NO_EDGE)
        self.assertGreater(len(out.capture_rows), 0)
        # capture 第一行应为 "clock CAPTURE_CLK" 而不是 "clock network delay ..."
        self.assertIn("clock", out.capture_rows[0]["point"])
        self.assertIn("CAPTURE_CLK", out.capture_rows[0]["point"])
        self.assertNotIn("network delay", out.capture_rows[0]["point"])

    def test_trigger_edge_extracted_from_path_tail(self):
        """input/output pin 的 Path 末尾 r/f 应写入 trigger_edge，并从 Path 中移除。"""
        rpt = FORMAT1_REPORT_TEMPLATE.format(
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


if __name__ == "__main__":
    unittest.main()

