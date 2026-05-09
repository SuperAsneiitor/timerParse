# -*- coding: utf-8 -*-
"""PT 解析器测试：trigger_edge 提取与基础路径解析。"""
from __future__ import annotations

import os
import tempfile
import unittest

import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.parser.pt_parser import PtParser


PT_REPORT_MINIMAL = r"""
  Startpoint: U_START/Q
  clocked by PTCLK
  Endpoint: U_END/D
  clocked by PTCLK

  Point                                                   Fanout  Cap      Trans    Derate   Incr     Path
  -------------------------------------------------------------------------------------------------------------
  clock PTCLK (rise edge)                                                          1.000     0.000    0.000
  U_START/Q (DFF)                                             1     0.001    0.010    1.000    0.050    0.050 r
  U_MID/A (BUF)                                               1     0.001    0.010    1.000    0.020    0.070 r
  data arrival time                                                                                     0.070

  clock PTCLK (rise edge)                                                          1.000     0.000    0.000
  U_END/D (DFF)                                               1     0.001    0.010    1.000    0.080    0.150 f
  library setup time                                                                                -0.010   -0.010
  data required time                                                                                  0.200
  slack (MET)                                                                                         0.050
"""

PT_REPORT_POINT_LAST_SUMMARY = r"""
  Startpoint: U_START/Q
              (rising edge-triggered flip-flop clocked by PTCLK)
  Endpoint: U_END/D
            (rising edge-triggered flip-flop clocked by PTCLK)
  Last common pin: U_START/Q
  Path Group: REG2REG
  Path Type: max

  Fanout      Cap     DTrans  Trans   Derate    Delta     Incr      Path      Voltage   Point
  ------------------------------------------------------------------------------------------------
                                                0.0000    0.0000    0.0000              clock PTCLK (rise edge)
                      0.0010  0.0100  1.1000    0.0000    0.0500 &  0.0500 r  0.9000    U_START/Q (DFF) <-
  3           0.0200                                      0.0199    0.0896 r            U_START/net0 (net)
                      0.0010  0.0100  1.1000    0.0000    0.0200 &  0.0700 r  0.9000    U123_MID/A (BUF) <-
                                                                    0.0700              data arrival time

                                                0.0000    0.0000    0.0000              clock PTCLK (rise edge)
                      0.0010  0.0100  1.1000    0.0000    0.0800 &  0.1500 f  0.9000    U_END/D (DFF)
                                                0.0000    0.0100    0.1600              library setup time
                                                                    0.1600              data required time
  ------------------------------------------------------------------------------------------------
                                                                    0.16                data required time
                                                                    -0.07               data arrival time
  ------------------------------------------------------------------------------------------------
                                                          0.00      0.00                statistical adjustment
                                                                    0.09                slack (MET)
"""


class TestPtParser(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = PtParser()

    def _parse_text(self, text: str):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".rpt", delete=False, encoding="utf-8") as f:
            f.write(text.lstrip("\n"))
            path = f.name
        try:
            return self.parser.parseReport(path)
        finally:
            os.unlink(path)

    def test_trigger_edge_extracted_from_path(self):
        out = self._parse_text(PT_REPORT_MINIMAL)
        self.assertGreater(len(out.launch_rows), 0)
        self.assertGreater(len(out.capture_rows), 0)
        launch_pin = next((r for r in out.launch_rows if "U_START/Q" in (r.get("point") or "")), None)
        capture_pin = next((r for r in out.capture_rows if "U_END/D" in (r.get("point") or "")), None)
        self.assertIsNotNone(launch_pin)
        self.assertIsNotNone(capture_pin)
        self.assertEqual(launch_pin.get("trigger_edge"), "r")
        self.assertEqual(capture_pin.get("trigger_edge"), "f")

    def test_summary_and_clocks(self):
        out = self._parse_text(PT_REPORT_MINIMAL)
        self.assertGreater(len(out.summary_rows), 0)
        s = out.summary_rows[0]
        self.assertEqual(s.get("startpoint_clock"), "PTCLK")
        self.assertEqual(s.get("endpoint_clock"), "PTCLK")
        self.assertEqual(s.get("arrival_time"), "0.070")
        self.assertEqual(s.get("required_time"), "0.200")

    def test_summary_values_when_point_column_is_last(self):
        """PT 生成版式中 summary label 在 Point 尾列时，也应按 Path 列取值。"""
        out = self._parse_text(PT_REPORT_POINT_LAST_SUMMARY)
        self.assertGreater(len(out.summary_rows), 0)
        s = out.summary_rows[0]
        self.assertEqual(s.get("arrival_time"), "0.0700")
        self.assertEqual(s.get("required_time"), "0.1600")
        self.assertEqual(s.get("slack"), "0.09")
        self.assertEqual(s.get("slack_status"), "MET")

    def test_point_last_fixed_columns_not_overwritten_by_cell_name_numbers(self):
        """Point 尾列含 cell 名数字时，固定列值和 trigger_edge 不应被 fallback 覆盖。"""
        out = self._parse_text(PT_REPORT_POINT_LAST_SUMMARY)
        launch_pin = next((r for r in out.launch_rows if "U_START/Q" in (r.get("point") or "")), None)
        launch_net = next((r for r in out.launch_rows if "U_START/net0" in (r.get("point") or "")), None)
        mid_pin = next((r for r in out.launch_rows if "U123_MID/A" in (r.get("point") or "")), None)
        capture_pin = next((r for r in out.capture_rows if "U_END/D" in (r.get("point") or "")), None)
        self.assertIsNotNone(launch_pin)
        self.assertIsNotNone(launch_net)
        self.assertIsNotNone(mid_pin)
        self.assertIsNotNone(capture_pin)
        self.assertEqual((launch_pin or {}).get("DTrans"), "0.0010")
        self.assertEqual((launch_pin or {}).get("Trans"), "0.0100")
        self.assertEqual((launch_pin or {}).get("Derate"), "1.1000")
        # Q 为 output_pin：PT 语义无 Delta，占位列不参与映射。
        self.assertEqual((launch_pin or {}).get("Delta"), "")
        self.assertEqual((launch_pin or {}).get("Incr"), "0.0500")
        self.assertEqual((launch_pin or {}).get("Path"), "0.0500")
        self.assertEqual((launch_pin or {}).get("Voltage"), "0.9000")
        self.assertEqual((launch_pin or {}).get("trigger_edge"), "r")
        self.assertEqual((launch_net or {}).get("point"), "U_START/net0 (net)")
        self.assertEqual(str((launch_net or {}).get("Fanout")), "3")
        self.assertEqual((launch_net or {}).get("Cap"), "0.0200")
        self.assertEqual((mid_pin or {}).get("trigger_edge"), "r")
        self.assertEqual((capture_pin or {}).get("trigger_edge"), "f")

    def test_point_last_misaligned_values_do_not_truncate_or_read_point_digits(self):
        """Point 尾列位置漂移时，数值从 point 前 token 提取，实例名数字不参与字段映射。"""
        rpt = PT_REPORT_POINT_LAST_SUMMARY.replace(
            "0.0010  0.0100  1.1000    0.0000    0.0200 &  0.0700 r  0.9000    U123_MID/A",
            "0.001000  0.010000  1.100000  0.000000  0.020000 &  0.070000 r  0.900000    U123_MID/A",
        )
        out = self._parse_text(rpt)
        mid_pin = next((r for r in out.launch_rows if "U123_MID/A" in (r.get("point") or "")), None)
        self.assertIsNotNone(mid_pin)
        self.assertEqual((mid_pin or {}).get("DTrans"), "0.0010")
        self.assertEqual((mid_pin or {}).get("Trans"), "0.0100")
        self.assertEqual((mid_pin or {}).get("Derate"), "1.1000")
        self.assertEqual((mid_pin or {}).get("Path"), "0.0700")
        self.assertEqual((mid_pin or {}).get("Voltage"), "0.9000")

    def test_output_pin_delta_empty_input_pin_keeps_delta(self):
        """output_pin（如寄存器 Q）不填 Delta；input_pin（如 D 端）保留 Delta 列。"""
        out = self._parse_text(PT_REPORT_POINT_LAST_SUMMARY)
        launch_q = next((r for r in out.launch_rows if "U_START/Q" in (r.get("point") or "")), None)
        capture_d = next((r for r in out.capture_rows if "U_END/D" in (r.get("point") or "")), None)
        self.assertIsNotNone(launch_q)
        self.assertIsNotNone(capture_d)
        self.assertEqual((launch_q or {}).get("Delta"), "")
        self.assertEqual((capture_d or {}).get("Delta"), "0.0000")


if __name__ == "__main__":
    unittest.main()

