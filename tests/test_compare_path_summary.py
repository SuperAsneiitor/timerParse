from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib import compare_path_summary as cps


class TestComparePathSummary(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.workdir = Path(self.tmpdir.name)
        self.golden = self.workdir / "golden.csv"
        self.test = self.workdir / "test.csv"

        golden_rows = [
            {"path_id": "1", "startpoint": "U1/A", "endpoint": "U2/Z", "arrival_time": "10", "required_time": "12", "slack": "2"},
            {"path_id": "2", "startpoint": "U3/A", "endpoint": "U4/Z", "arrival_time": "20", "required_time": "25", "slack": "5"},
            {"path_id": "3", "startpoint": "U5/A", "endpoint": "U6/Z", "arrival_time": "5", "required_time": "8", "slack": "3"},
        ]
        test_rows = [
            {"path_id": "1", "startpoint": "U1/A", "endpoint": "U2/Z", "arrival_time": "11", "required_time": "13", "slack": "2.5"},
            {"path_id": "2", "startpoint": "U3/A", "endpoint": "U4/Z", "arrival_time": "18", "required_time": "26", "slack": "4"},
            {"path_id": "3", "startpoint": "U5/A", "endpoint": "U6/Z", "arrival_time": "5.5", "required_time": "7.2", "slack": "2.7"},
        ]
        self._write_csv(self.golden, golden_rows)
        self._write_csv(self.test, test_rows)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def _write_csv(self, path: Path, rows: list[dict]) -> None:
        fieldnames = ["path_id", "startpoint", "endpoint", "arrival_time", "required_time", "slack"]
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def _run_cli(self, args: list[str]) -> subprocess.CompletedProcess:
        script = Path(__file__).resolve().parents[1] / "scripts" / "compare_path_summary.py"
        cmd = [sys.executable, str(script), str(self.golden), str(self.test)] + args
        return subprocess.run(cmd, capture_output=True, text=True, check=False)

    def test_compute_stats_quantile_threshold_and_correlation(self):
        result = cps.compare(cps.load_summary(str(self.golden)), cps.load_summary(str(self.test)))
        self.assertEqual(result[0]["arrival_time_ratio"], "10.000%")
        self.assertEqual(result[0]["required_time_ratio"], "8.333%")
        self.assertEqual(result[0]["slack_diff"], "0.500000")

        stats = cps.compute_stats(result, threshold=5)

        self.assertEqual(stats["sample_count"], 3)
        self.assertIn("arrival_time_ratio", stats["metrics"])
        self.assertIn("required_time_ratio", stats["metrics"])
        self.assertIn("slack_diff", stats["metrics"])

        arrival = stats["metrics"]["arrival_time_ratio"]
        self.assertEqual(arrival["count"], 3)
        self.assertEqual(arrival["mean"], 10.0)
        self.assertIsNotNone(arrival["p90"])
        self.assertIsNotNone(arrival["p95"])
        self.assertIsNotNone(arrival["p99"])
        self.assertEqual(arrival["threshold"]["value"], 5)
        self.assertEqual(arrival["threshold"]["count"], 3)

        corr = stats["correlations"]["arrival_time_ratio__required_time_ratio"]
        self.assertEqual(corr["count"], 3)
        self.assertIsNotNone(corr["pearson"])

    def test_cli_default_outputs_without_charts_and_html(self):
        out = self.workdir / "compare_result.csv"
        proc = self._run_cli(["-o", str(out), "--no-charts", "--no-html"])
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)

        simple = self.workdir / "compare_result_simple.csv"
        stats_json = self.workdir / "compare_stats.json"
        self.assertTrue(out.is_file())
        self.assertTrue(simple.is_file())
        self.assertTrue(stats_json.is_file())
        self.assertFalse((self.workdir / "compare_report.html").exists())

        with open(stats_json, "r", encoding="utf-8") as f:
            stats = json.load(f)
        self.assertIn("metrics", stats)
        self.assertIn("correlations", stats)

    def test_cli_custom_stats_and_chart_and_html_outputs(self):
        try:
            import matplotlib  # noqa: F401
        except Exception:
            self.skipTest("matplotlib not available for chart generation test")

        out = self.workdir / "out" / "compare_result.csv"
        stats_json = self.workdir / "out" / "my_stats.json"
        stats_csv = self.workdir / "out" / "my_stats.csv"
        charts_dir = self.workdir / "out" / "my_charts"

        proc = self._run_cli(
            [
                "-o",
                str(out),
                "--threshold",
                "5",
                "--bins",
                "20",
                "--stats-json",
                str(stats_json),
                "--stats-csv",
                str(stats_csv),
                "--charts-dir",
                str(charts_dir),
            ]
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)

        html = out.parent / "compare_report.html"
        self.assertTrue(stats_json.is_file())
        self.assertTrue(stats_csv.is_file())
        self.assertTrue(html.is_file())
        self.assertTrue(charts_dir.is_dir())

        expected_chart_files = [
            "hist_arrival_time_ratio.png",
            "hist_required_time_ratio.png",
            "hist_slack_diff.png",
            "boxplot_ratios.png",
            "scatter_arrival_time_ratio_vs_required_time_ratio.png",
            "scatter_arrival_time_ratio_vs_slack_diff.png",
            "scatter_required_time_ratio_vs_slack_diff.png",
        ]
        for name in expected_chart_files:
            self.assertTrue((charts_dir / name).is_file(), msg=f"missing chart: {name}")

        html_text = html.read_text(encoding="utf-8")
        self.assertIn("统计摘要", html_text)
        self.assertIn("阈值超限摘要", html_text)
        self.assertIn("相关性摘要", html_text)
        self.assertIn("图表", html_text)
        self.assertIn("%", html_text)

    def test_slack_pass_abs_diff_under_5ps(self):
        """abs(slack_diff) < 5ps -> PASS（不依赖 AT_ref/clock_period）。"""
        golden_rows = [
            {
                "path_id": "1",
                "startpoint": "U1/A",
                "endpoint": "U2/Z",
                "arrival_time": "10",
                "required_time": "12",
                "slack": "10",
                "common_pin_delay": "0",
                "clock_period": "100",
            }
        ]
        test_rows = [
            {
                "path_id": "1",
                "startpoint": "U1/A",
                "endpoint": "U2/Z",
                "arrival_time": "10",
                "required_time": "12",
                "slack": "14",  # slack_diff = +4
                "common_pin_delay": "0",
                "clock_period": "100",
            }
        ]
        result = cps.compare(golden_rows, test_rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].get("slack_pass"), "PASS")
        self.assertEqual(result[0].get("AT_ref"), "")
        self.assertEqual(result[0].get("slack_diff_AT_ref_ratio"), "")

    def test_slack_pass_when_golden_slack_le_0_fails(self):
        """abs(slack_diff) >= 5ps 且 golden_slack <= 0 -> FAIL。"""
        golden_rows = [
            {
                "path_id": "1",
                "startpoint": "U1/A",
                "endpoint": "U2/Z",
                "arrival_time": "10",
                "required_time": "12",
                "slack": "-1",
                "common_pin_delay": "0",
                "clock_period": "100",
            }
        ]
        test_rows = [
            {
                "path_id": "1",
                "startpoint": "U1/A",
                "endpoint": "U2/Z",
                "arrival_time": "10",
                "required_time": "12",
                "slack": "6",  # slack_diff = +7
                "common_pin_delay": "0",
                "clock_period": "100",
            }
        ]
        result = cps.compare(golden_rows, test_rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].get("slack_pass"), "FAIL")

    def test_slack_pass_ratio_both_under_5pct(self):
        """golden_slack > 0 时：abs(slack_diff/AT_ref) < 5% 且 abs(slack_diff/clock_period) < 5% -> PASS。"""
        golden_rows = [
            {
                "path_id": "1",
                "startpoint": "U1/A",
                "endpoint": "U2/Z",
                "arrival_time": "210",
                "required_time": "12",
                "slack": "10",
                "common_pin_delay": "10",  # AT_ref = 210 - 10 = 200
                "clock_period": "200",
            }
        ]
        test_rows = [
            {
                "path_id": "1",
                "startpoint": "U1/A",
                "endpoint": "U2/Z",
                "arrival_time": "210",
                "required_time": "12",
                "slack": "16",  # slack_diff = +6
                "common_pin_delay": "10",
                "clock_period": "200",
            }
        ]
        result = cps.compare(golden_rows, test_rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].get("slack_pass"), "PASS")
        self.assertEqual(result[0].get("slack_diff_AT_ref_ratio"), "3.000%")
        self.assertEqual(result[0].get("slack_diff_clock_period_ratio"), "3.000%")

    def test_slack_pass_ratio_one_over_5pct_fails(self):
        """当其中一个比值 >= 5% -> FAIL。"""
        golden_rows = [
            {
                "path_id": "1",
                "startpoint": "U1/A",
                "endpoint": "U2/Z",
                "arrival_time": "210",
                "required_time": "12",
                "slack": "10",
                "common_pin_delay": "10",  # AT_ref = 200
                "clock_period": "100",
            }
        ]
        test_rows = [
            {
                "path_id": "1",
                "startpoint": "U1/A",
                "endpoint": "U2/Z",
                "arrival_time": "210",
                "required_time": "12",
                "slack": "16",  # slack_diff = +6
                "common_pin_delay": "10",
                "clock_period": "100",
            }
        ]
        result = cps.compare(golden_rows, test_rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].get("slack_pass"), "FAIL")
        self.assertEqual(result[0].get("slack_diff_AT_ref_ratio"), "3.000%")
        self.assertEqual(result[0].get("slack_diff_clock_period_ratio"), "6.000%")

    def test_cli_detail_topn_generates_only_topn_detail_pages(self):
        """--detail-scope topN 只为 Top-N 生成 paths/path_*.html。"""
        def write_launch_csv(path: Path) -> None:
            # 只提供 loadSegmentCsvByPathId / buildPointSegmentHtml 需要的最小字段
            fieldnames = ["path_id", "point_index", "point"]
            rows = []
            for pid in ("1", "2", "3"):
                rows.append({"path_id": pid, "point_index": "1", "point": "p_clk"})
                rows.append({"path_id": pid, "point_index": "2", "point": "p_data"})
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fieldnames)
                w.writeheader()
                w.writerows(rows)

        golden_launch = self.workdir / "golden_launch_path.csv"
        test_launch = self.workdir / "test_launch_path.csv"
        write_launch_csv(golden_launch)
        write_launch_csv(test_launch)

        out_dir = self.workdir / "topn_out"
        out = out_dir / "compare_result.csv"

        proc = self._run_cli(
            [
                "-o",
                str(out),
                "--no-charts",
                "--detail-scope",
                "topN",
                "--detail-top-n",
                "2",
                "--golden-launch-csv",
                str(golden_launch),
                "--test-launch-csv",
                str(test_launch),
            ]
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)

        paths_dir = out_dir / "paths"
        self.assertTrue(paths_dir.is_dir())
        # top2 应对应 path_1.html / path_2.html（默认按 slack_diff abs 降序）
        self.assertTrue((paths_dir / "path_1.html").is_file())
        self.assertTrue((paths_dir / "path_2.html").is_file())
        self.assertFalse((paths_dir / "path_3.html").exists())


if __name__ == "__main__":
    unittest.main()
