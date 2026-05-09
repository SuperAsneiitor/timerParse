# -*- coding: utf-8 -*-
"""端到端：PT 报告与抽取 CSV 中 output pin 行不应出现 DTrans/Delta 数值。"""
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
    """覆盖 PT 流程中 DTrans/Delta 仅出现在 input pin 的语义。"""

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
            dtrans_pos = header_line.index("DTrans")
            trans_pos = header_line.index("Trans")
            delta_pos = header_line.index("Delta")
            delta_end = delta_pos + len("Delta")

            checked = 0
            body_lines = lines[header_idx + 1 :]
            for idx, ln in enumerate(body_lines):
                # 只看含有 " <-" 的 launch 数据段 pin 行（PT 用 " <-" 标记 launch 段经过的 pin）。
                if " <-" not in ln:
                    continue
                if not re.search(r"/[A-Za-z0-9_\[\]]+\s*\(", ln):
                    continue
                next_line = next((x for x in body_lines[idx + 1 :] if x.strip()), "")
                # timing path 拓扑：net 前一个实例 pin 是 output pin，不依赖 pin 名称白名单。
                if "(net)" not in next_line:
                    continue
                dtrans_segment = ln[dtrans_pos:trans_pos] if trans_pos <= len(ln) else ""
                self.assertEqual(
                    dtrans_segment.strip(),
                    "",
                    f"PT 报告中 output pin 的 DTrans 列应为空，得到 {dtrans_segment!r} (line: {ln!r})",
                )
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
                    rows = list(csv.DictReader(f))
                    out_pin_rows = 0
                    for idx, row in enumerate(rows):
                        point = (row.get("point") or "").strip()
                        if " <-" not in point:
                            continue
                        if not re.search(r"/[A-Za-z0-9_\[\]]+\s*\(", point):
                            continue
                        next_point = ""
                        for next_row in rows[idx + 1 :]:
                            if next_row.get("path_id") != row.get("path_id"):
                                break
                            next_point = (next_row.get("point") or "").strip()
                            if next_point:
                                break
                        # timing path 拓扑：net 前一个实例 pin 是 output pin。
                        if "(net)" not in next_point:
                            continue
                        dtrans_val = (row.get("DTrans") or "").strip()
                        self.assertEqual(
                            dtrans_val, "",
                            f"{csv_name}: output pin DTrans 应为空，得到 {dtrans_val!r} (point={point!r})",
                        )
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
