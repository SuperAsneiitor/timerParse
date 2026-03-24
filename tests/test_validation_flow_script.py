from __future__ import annotations

import shutil
import subprocess
import sys
import unittest
from pathlib import Path


class TestValidationFlowScript(unittest.TestCase):
    def test_validation_flow_generates_report_timing_tcl(self):
        """验证 run_validation_flow 会产出 gen-pt 的 report_timing 脚本。"""
        repo_root = Path(__file__).resolve().parents[1]
        out_rel = "test_results/validation_flow_ci_case"
        out_dir = repo_root / out_rel

        if out_dir.exists():
            shutil.rmtree(out_dir)

        cmd = [
            sys.executable,
            "scripts/run_validation_flow.py",
            "--jobs",
            "2",
            "--output-base",
            out_rel,
        ]
        proc = subprocess.run(cmd, cwd=str(repo_root), capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 0, msg=proc.stderr or proc.stdout)

        tcl_f1 = out_dir / "reports" / "report_timing_format1.tcl"
        tcl_f2 = out_dir / "reports" / "report_timing_format2.tcl"
        tcl_pt = out_dir / "reports" / "report_timing_pt.tcl"
        for p in (tcl_f1, tcl_f2, tcl_pt):
            self.assertTrue(p.is_file(), f"缺少 gen-pt 产物: {p}")

        for text in (
            tcl_f1.read_text(encoding="utf-8"),
            tcl_f2.read_text(encoding="utf-8"),
            tcl_pt.read_text(encoding="utf-8"),
        ):
            self.assertIn("-delay_type max -path_type full_clock", text)
            self.assertIn("set output_file", text)
            self.assertIn("-rise_through", text)


if __name__ == "__main__":
    unittest.main()
