# -*- coding: utf-8 -*-
"""端到端：PT 报告与抽取 CSV 中 output pin 行不应出现 Delta 数值。"""
from __future__ import annotations

import csv
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


_ROOT = Path(__file__).resolve().parents[1]


def _run(args: list[str]) -> None:
    proc = subprocess.run(args, cwd=str(_ROOT), capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise AssertionError(
            f"command failed (exit={proc.returncode}): {' '.join(args)}\n"
            f"stdout=\n{proc.stdout}\nstderr=\n{proc.stderr}"
        )


class TestPtOutputPinNoDelta(unittest.TestCase):
    """覆盖 PT 流程中 Delta 仅出现在 input pin 的语义。"""

    def test_generated_pt_report_and_csv_have_empty_delta_for_output_pin(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            rpt = tmp / "gen_pt.rpt"
            extract_dir = tmp / "extract_pt"

            _run([
                sys.executable, "-m", "lib", "gen-report",
                "config/gen_report/pt.yaml",
                "--seed", "101",
                "-o", str(rpt),
            ])
            _run([
                sys.executable, "-m", "lib", "extract",
                str(rpt), "-o", str(extract_dir), "-f", "pt", "-j", "1",
            ])

            text = rpt.read_text(encoding="utf-8")
            header_re = re.compile(
                r"^\s*Fanout\s+Cap\s+DTrans\s+Trans\s+Derate\s+Delta\s+Incr\s+Path\s+Voltage\s+Point\s*$"
            )
            lines = text.splitlines()
            header_idx = next((i for i, ln in enumerate(lines) if header_re.match(ln)), -1)
            self.assertGreaterEqual(header_idx, 0, "未找到 PT 表头")

            header_line = lines[header_idx]
            delta_pos = header_line.index("Delta")
            delta_end = delta_pos + len("Delta")

            checked = 0
            for ln in lines[header_idx + 1 :]:
                # 只看含有 " <-" 的 launch 数据段 pin 行（PT 用 " <-" 标记 launch 段经过的 pin）。
                # 取所有 pin 行（input/output 都标 <-），通过 trailing token 判断是否为 output（pin 名结尾为 Z/ZN/Q/Y 等）。
                if " <-" not in ln:
                    continue
                # 行尾可能有 cell 注释，去掉以提取 pin 名。
                point_part = ln.rsplit(" <-", 1)[0].rstrip()
                m = re.search(r"/([A-Za-z0-9_]+)\s*\(", point_part)
                if not m:
                    continue
                pin = m.group(1)
                if pin not in {"Z", "ZN", "ZP", "Q", "Y", "YN"}:
                    continue
                segment = ln[delta_pos:delta_end] if delta_end <= len(ln) else ""
                self.assertEqual(
                    segment.strip(),
                    "",
                    f"PT 报告中 output pin 的 Delta 列应为空，得到 {segment!r} (line: {ln!r})",
                )
                checked += 1
            self.assertGreater(checked, 0, "未在 PT 报告中扫描到任何 output pin 行")

            for csv_name in ("launch_path.csv", "capture_path.csv", "data_path.csv"):
                csv_path = extract_dir / csv_name
                self.assertTrue(csv_path.exists(), f"缺少 {csv_path}")
                with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
                    reader = csv.DictReader(f)
                    out_pin_rows = 0
                    for row in reader:
                        point = (row.get("point") or "").strip()
                        if " <-" not in point:
                            continue
                        m = re.search(r"/([A-Za-z0-9_]+)\s*\(", point)
                        if not m:
                            continue
                        pin = m.group(1)
                        if pin not in {"Z", "ZN", "ZP", "Q", "Y", "YN"}:
                            continue
                        delta_val = (row.get("Delta") or "").strip()
                        self.assertEqual(
                            delta_val, "",
                            f"{csv_name}: output pin Delta 应为空，得到 {delta_val!r} (point={point!r})",
                        )
                        out_pin_rows += 1
                    if csv_name == "data_path.csv":
                        self.assertGreater(
                            out_pin_rows, 0,
                            f"{csv_name}: 未扫描到任何 output pin 行，疑似 point 列异常",
                        )


if __name__ == "__main__":
    unittest.main()
