# -*- coding: utf-8 -*-
"""compare 单路径详情页逐点字段展示测试。"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.compare.path_detail_html import buildPointSegmentHtml


class TestPathDetailHtml(unittest.TestCase):
    def test_point_table_includes_pt_optional_fields(self) -> None:
        """逐点列表展示 PT 常用字段；缺失字段保持为空单元格。"""
        html = buildPointSegmentHtml(
            "Launch path 逐点对比",
            [
                {
                    "point": "u0/Z (BUF)",
                    "Fanout": "3",
                    "DTrans": "0.0010",
                    "Delta": "",
                    "Voltage": "0.9000",
                }
            ],
            [{"point": "u0/Z (BUF)"}],
        )
        for header in ("Fanout", "DTrans", "Delta", "Voltage"):
            self.assertIn(f">{header}<", html)
        self.assertIn(">3<", html)
        self.assertIn(">0.0010<", html)
        self.assertIn(">0.9000<", html)
        self.assertIn("<td></td>", html)


if __name__ == "__main__":
    unittest.main()
