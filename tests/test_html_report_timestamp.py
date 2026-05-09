# -*- coding: utf-8 -*-
"""compare HTML 报告：顶端生成时间戳渲染。"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.compare.html_report import generate_html_report


_TS_RE = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")


class TestHtmlReportTimestamp(unittest.TestCase):
    def _buildMinimalArgs(self, out_dir: Path) -> dict:
        return dict(
            html_path=out_dir / "compare_report.html",
            golden_path=Path("golden.csv"),
            test_path=Path("test.csv"),
            compared_count=2,
            stats={
                "metrics": {},
                "segment_metrics": {},
                "error_range_stats": {},
                "slack_pass_stats": {
                    "pass_count": 2,
                    "fail_count": 0,
                    "pass_ratio": 1.0,
                    "unknown_count": 0,
                },
            },
            chart_files={},
            charts_dir=out_dir / "charts",
            rows=[
                {
                    "path_id": "1",
                    "startpoint": "u0/Q",
                    "endpoint": "u1/D",
                    "slack_diff": "0.01",
                },
                {
                    "path_id": "2",
                    "startpoint": "u2/Q",
                    "endpoint": "u3/D",
                    "slack_diff": "-0.02",
                },
            ],
            page_size=1,
            sort_by="slack_diff",
            sort_abs=True,
            detail_scope="none",
        )

    def test_summary_and_pages_have_generated_at_badge(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td)
            (out_dir / "charts").mkdir(parents=True, exist_ok=True)
            generate_html_report(**self._buildMinimalArgs(out_dir))

            summary_html = (out_dir / "compare_report.html").read_text(encoding="utf-8")
            self.assertIn("report-header", summary_html)
            self.assertIn("生成时间", summary_html)
            self.assertRegex(summary_html, _TS_RE)

            page_files = sorted((out_dir / "pages").glob("page_*.html"))
            self.assertGreaterEqual(len(page_files), 2, "应生成至少 2 个分页页")
            for p in page_files:
                page_html = p.read_text(encoding="utf-8")
                self.assertIn("report-header", page_html)
                self.assertIn("生成时间", page_html)
                self.assertRegex(page_html, _TS_RE)


if __name__ == "__main__":
    unittest.main()
