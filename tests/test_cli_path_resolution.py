from __future__ import annotations

import os
import unittest
from argparse import Namespace
from unittest import mock

from lib.cli import _resolveCommandPaths, resolveUserPath


class TestCliPathResolution(unittest.TestCase):
    """验证 lake/CLI 的相对路径始终按用户调用目录解释。"""

    def testResolveUserPathUsesLakeCallerCwd(self):
        with mock.patch.dict(os.environ, {"LAKE_CALLER_CWD": r"C:\tmp\caller"}, clear=False):
            with mock.patch("os.path.isdir", return_value=True):
                resolved = resolveUserPath(r"input\demo.rpt")
        self.assertEqual(
            resolved,
            os.path.abspath(r"C:\tmp\caller\input\demo.rpt"),
        )

    def testResolveUserPathKeepsAbsolutePath(self):
        abs_path = os.path.abspath(r"C:\tmp\caller\input\demo.rpt")
        self.assertEqual(resolveUserPath(abs_path), abs_path)

    def testResolveCompareCommandPaths(self):
        args = Namespace(
            command="compare",
            golden_file="golden/path_summary.csv",
            test_file="test/path_summary.csv",
            golden_file_opt="",
            test_file_opt="",
            output="out/result.csv",
            charts_dir="out/charts",
            stats_json="out/stats.json",
            stats_csv="",
            golden_launch_csv="golden/launch.csv",
            test_launch_csv="test/launch.csv",
            golden_capture_csv="",
            test_capture_csv="",
        )
        with mock.patch.dict(os.environ, {"LAKE_CALLER_CWD": r"C:\tmp\caller"}, clear=False):
            with mock.patch("os.path.isdir", return_value=True):
                _resolveCommandPaths(args)
        self.assertEqual(args.golden_file, os.path.abspath(r"C:\tmp\caller\golden\path_summary.csv"))
        self.assertEqual(args.test_file, os.path.abspath(r"C:\tmp\caller\test\path_summary.csv"))
        self.assertEqual(args.output, os.path.abspath(r"C:\tmp\caller\out\result.csv"))
        self.assertEqual(args.charts_dir, os.path.abspath(r"C:\tmp\caller\out\charts"))
        self.assertEqual(args.stats_json, os.path.abspath(r"C:\tmp\caller\out\stats.json"))


if __name__ == "__main__":
    unittest.main()
