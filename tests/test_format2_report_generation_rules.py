# -*- coding: utf-8 -*-
"""Format2 合成报告生成端字段规则测试。"""
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


class TestFormat2ReportGenerationRules(unittest.TestCase):
    def test_output_pin_has_no_dtrans_or_ddelay(self) -> None:
        """format2 output pin 的 D-Trans/D-Delay 为空，input pin 保留这两个字段。"""
        with tempfile.TemporaryDirectory() as td:
            rpt = Path(td) / "gen_format2.rpt"
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "lib",
                    "gen-report",
                    "config/gen_report/format2.yaml",
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
            header = next(line for line in lines if line.startswith("Type") and "D-Trans" in line)
            input_line = next(line for line in lines if "/u0/CK " in line and line.startswith("pin"))
            output_line = next(line for line in lines if "/u0/Z " in line and line.startswith("pin"))
            starts = {
                m.group(0): m.start()
                for m in re.finditer(r"\S+", header)
                if m.group(0) in ("D-Trans", "Trans", "D-Delay", "Delay", "Time", "Description")
            }

            def cell(line: str, col: str, next_col: str) -> str:
                return line[starts[col] : starts[next_col]].strip()

            self.assertEqual(cell(input_line, "D-Trans", "Trans"), "-0.0000")
            self.assertEqual(cell(input_line, "D-Delay", "Delay"), "-0.0000")
            self.assertEqual(cell(output_line, "D-Trans", "Trans"), "")
            self.assertEqual(cell(output_line, "D-Delay", "Delay"), "")


if __name__ == "__main__":
    unittest.main()
