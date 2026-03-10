# -*- coding: utf-8 -*-
"""PT 解析器测试：trigger_edge 提取与基础路径解析。"""
from __future__ import annotations

import os
import tempfile
import unittest

import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.pt_parser import PtParser


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


class TestPtParser(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = PtParser()

    def _parse_text(self, text: str):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".rpt", delete=False, encoding="utf-8") as f:
            f.write(text.lstrip("\n"))
            path = f.name
        try:
            return self.parser.parse_report(path)
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


if __name__ == "__main__":
    unittest.main()

