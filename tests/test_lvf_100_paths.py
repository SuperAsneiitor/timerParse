# -*- coding: utf-8 -*-
"""100 条 format1 LVF 合成报告：解析完整性（path_summary 行数）与 LVF 字段存在性。"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.parser.format1_parser import Format1Parser
from tests.format1_lvf_synth import DEFAULT_EXTRA_DATA_GROUPS, buildFormat1LvfReport


class TestLvf100PathsSynthetic(unittest.TestCase):
    def test_100_paths_parse_and_lvf_fields(self) -> None:
        text = buildFormat1LvfReport(100)
        parser = Format1Parser()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".rpt", delete=False, encoding="utf-8") as f:
            f.write(text)
            path = f.name
        try:
            out = parser.parseReport(path)
        finally:
            os.unlink(path)

        self.assertEqual(len(out.summary_rows), 100)
        self.assertGreater(len(out.launch_rows), 0)
        self.assertGreater(len(out.capture_rows), 0)
        # 长 data_path：Startpoint 起 + 每组 (in/out/net) + data arrival（见 format1_lvf_synth）
        expected_dp_points = 2 + 3 * DEFAULT_EXTRA_DATA_GROUPS
        dp_counts = [int(r["data_path_point_count"]) for r in out.summary_rows]
        self.assertTrue(all(c >= expected_dp_points for c in dp_counts), f"data_path 点数应 >= {expected_dp_points}，实际 min={min(dp_counts)}")
        self.assertEqual(len(out.data_path_rows), 100 * expected_dp_points)
        # 任取一条 pin 行应含 LVF 拆分列
        pin_like = [r for r in out.launch_rows if "TransMean" in r and str(r.get("TransMean", "")).strip()]
        self.assertTrue(pin_like, "launch 中应有带 TransMean 的 pin 行")
