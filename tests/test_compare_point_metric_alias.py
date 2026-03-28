from __future__ import annotations

import unittest

from lib.compare.path_detail_html import buildPointSegmentHtml


class TestComparePointMetricAlias(unittest.TestCase):
    def test_unified_metric_columns_for_incr_delay_and_time_path(self):
        rows_g = [
            {
                "point": "p1",
                "Incr": "0.010",
                "Path": "0.100",
                "Type": "pin",
            }
        ]
        rows_t = [
            {
                "point": "p1",
                "Delay": "0.012",
                "Time": "0.102",
                "Type": "pin",
            }
        ]
        html = buildPointSegmentHtml("Launch", rows_g, rows_t)
        self.assertIn("<th colspan='3'>Incr</th>", html)
        self.assertIn("<th colspan='3'>Time</th>", html)
        self.assertIn("<th>G</th><th>T</th><th>Δ</th>", html)
        self.assertNotIn("StepDelay(Incr/Delay)", html)
        self.assertNotIn("PathTime(Path/Time)", html)
        self.assertNotIn("<th colspan='3'>Type</th>", html)
        self.assertNotIn("<th colspan='3'>Fanout</th>", html)
        self.assertNotIn("<th colspan='3'>Description</th>", html)
        self.assertIn("0.010", html)
        self.assertIn("0.012", html)
        self.assertIn("0.100", html)
        self.assertIn("0.102", html)


if __name__ == "__main__":
    unittest.main()
