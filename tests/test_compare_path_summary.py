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

from scripts import compare_path_summary as cps


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
        self.assertTrue(result[0]["arrival_time_ratio"].endswith("%"))
        self.assertTrue(result[0]["required_time_ratio"].endswith("%"))
        self.assertTrue(result[0]["slack_ratio"].endswith("%"))

        stats = cps.compute_stats(result, threshold=5)

        self.assertEqual(stats["sample_count"], 3)
        self.assertIn("arrival_time_ratio", stats["metrics"])
        self.assertIn("required_time_ratio", stats["metrics"])
        self.assertIn("slack_ratio", stats["metrics"])

        arrival = stats["metrics"]["arrival_time_ratio"]
        self.assertEqual(arrival["count"], 3)
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
            "hist_slack_ratio.png",
            "boxplot_ratios.png",
            "scatter_arrival_time_ratio_vs_required_time_ratio.png",
            "scatter_arrival_time_ratio_vs_slack_ratio.png",
            "scatter_required_time_ratio_vs_slack_ratio.png",
        ]
        for name in expected_chart_files:
            self.assertTrue((charts_dir / name).is_file(), msg=f"missing chart: {name}")

        html_text = html.read_text(encoding="utf-8")
        self.assertIn("统计摘要", html_text)
        self.assertIn("阈值超限摘要", html_text)
        self.assertIn("相关性摘要", html_text)
        self.assertIn("图表", html_text)
        self.assertIn("%", html_text)


if __name__ == "__main__":
    unittest.main()
