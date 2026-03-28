# -*- coding: utf-8 -*-
"""轻量布局运行时测试。"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.parser_V2.layout_runtime import LayoutRuntime


class TestLayoutRuntime(unittest.TestCase):
    def test_classify_format2_clock(self):
        rt = LayoutRuntime("format2")
        line = "clock                                                   0.026     0.026       clock pll_cpu_clk (rise edge)"
        self.assertEqual(rt.classifyPointType(line, type_hint="clock"), "clock")

    def test_extract_tail_numeric_and_point(self):
        rt = LayoutRuntime("format2")
        line = "constraint                                              0.042     0.551       library setup time"
        got = rt.extractByTypeLayout("constraint", line)
        self.assertEqual(got.get("Delay"), "0.042")
        self.assertEqual(got.get("Time"), "0.551")
        self.assertIn("library setup time", got.get("point", ""))

    def test_row_kind_numeric_pt(self):
        rt = LayoutRuntime("pt")
        line = "clock source latency                                                                          0.0026    0.0159    0.0175    0.0222"
        got = rt.extractRowKindNumeric("clock_src_lat", line)
        self.assertEqual(got, {"Mean": "0.0026", "Sensit": "0.0159", "Incr": "0.0175", "Path": "0.0222"})


if __name__ == "__main__":
    unittest.main()
