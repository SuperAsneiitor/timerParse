# -*- coding: utf-8 -*-
"""PT 合成报告生成端列对齐测试。"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


_ROOT = Path(__file__).resolve().parents[1]


class TestPtReportGenerationAlignment(unittest.TestCase):
    def test_values_keep_header_columns_when_dtrans_and_delta_are_empty(self) -> None:
        """output pin 无 DTrans/Delta 时，后续 Trans/Incr/Path/Voltage 仍落在对应列名下。"""
        with tempfile.TemporaryDirectory() as td:
            rpt = Path(td) / "gen_pt.rpt"
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "lib",
                    "gen-report",
                    "config/gen_report/pt.yaml",
                    "--seed",
                    "101",
                    "-o",
                    str(rpt),
                ],
                cwd=str(_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)

            lines = rpt.read_text(encoding="utf-8").splitlines()
            header = next(line for line in lines if "Fanout" in line and "DTrans" in line and "Point" in line)
            output_line = next(line for line in lines if "x_ct_top_0/path_1/u0/Z " in line and "<-" in line)

            starts = {
                m.group(0): m.start()
                for m in re.finditer(r"\S+", header)
                if m.group(0) in ("DTrans", "Trans", "Derate", "Delta", "Incr", "Path", "Voltage", "Point")
            }

            def cell(line: str, col: str, next_col: str) -> str:
                return line[starts[col] : starts[next_col]].strip()

            self.assertEqual(cell(output_line, "DTrans", "Trans"), "")
            self.assertEqual(cell(output_line, "Trans", "Derate"), "0.0086")
            self.assertEqual(cell(output_line, "Derate", "Delta"), "1.1000")
            self.assertEqual(cell(output_line, "Delta", "Incr"), "")
            self.assertTrue(cell(output_line, "Incr", "Path").startswith("0.0062"))
            self.assertEqual(cell(output_line, "Path", "Voltage"), "0.0598 r")
            self.assertEqual(cell(output_line, "Voltage", "Point"), "0.8217")


if __name__ == "__main__":
    unittest.main()
