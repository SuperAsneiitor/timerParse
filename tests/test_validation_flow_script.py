from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest
import csv
from collections import defaultdict
from pathlib import Path


class TestValidationFlowScript(unittest.TestCase):
    def _readCsvRows(self, csv_path: Path) -> list[dict[str, str]]:
        """读取 CSV 并去除 BOM，返回行列表。"""
        with csv_path.open("r", encoding="utf-8", newline="") as f:
            return [
                {str(k).lstrip("\ufeff"): (v or "") for k, v in row.items()}
                for row in csv.DictReader(f)
            ]

    def _assertExtractArtifacts(self, out_dir: Path, fmt: str) -> None:
        """校验某格式的 extract 产物完整性。"""
        extract_dir = out_dir / f"extract_{fmt}"
        self.assertTrue(extract_dir.is_dir(), f"缺少 extract 目录: {extract_dir}")
        for name in (
            "launch_path.csv",
            "capture_path.csv",
            "launch_clock_path.csv",
            "data_path.csv",
            "path_summary.csv",
        ):
            self.assertTrue((extract_dir / name).is_file(), f"缺少 extract 文件: {extract_dir / name}")

    def _assertCompareStats(self, stats_json: Path, expected_count: int) -> None:
        """校验 compare 统计 JSON 基本结构与样本数。"""
        self.assertTrue(stats_json.is_file(), f"缺少 compare stats: {stats_json}")
        stats = json.loads(stats_json.read_text(encoding="utf-8"))
        self.assertEqual(int(stats.get("sample_count") or 0), expected_count, f"{stats_json} sample_count 异常")
        numeric_counts = stats.get("numeric_counts") or {}
        for key in ("arrival_time_ratio", "required_time_ratio", "slack_diff"):
            self.assertEqual(
                int(numeric_counts.get(key) or 0),
                expected_count,
                f"{stats_json} numeric_counts[{key}] 异常",
            )

    def _assertFormat2DerateCoverage(self, out_dir: Path) -> None:
        """校验 format2 的 pin Derate 覆盖率，防止 Derate 解析回归。"""
        launch_csv = out_dir / "extract_format2" / "launch_path.csv"
        capture_csv = out_dir / "extract_format2" / "capture_path.csv"
        rows = self._readCsvRows(launch_csv) + self._readCsvRows(capture_csv)
        pin_rows = [
            r for r in rows if str(r.get("Type") or "").strip().lower() == "pin"
        ]
        self.assertGreater(len(pin_rows), 0, "format2 pin 行为空，无法检查 Derate 覆盖率")
        non_empty = [
            r for r in pin_rows if str(r.get("Derate") or "").strip() != ""
        ]
        coverage = len(non_empty) / len(pin_rows)
        self.assertGreaterEqual(
            coverage,
            0.98,
            f"format2 pin Derate 覆盖率过低: {coverage:.3f}",
        )
        # 单值 Derate 基线：至少应出现 0.900（避免误解析成 Time）
        self.assertTrue(
            any(abs(float(str(r.get("Derate") or "").strip()) - 0.9) < 1e-9 for r in non_empty if str(r.get("Derate") or "").strip()),
            "format2 Derate 未出现单值 0.900x，可能发生列错位解析",
        )

    def _assertFormat2CaptureTail(self, out_dir: Path) -> None:
        """校验 format2 capture 必含 endpoint CK，且后续仅允许约束尾部行。"""
        capture_csv = out_dir / "extract_format2" / "capture_path.csv"
        rows = self._readCsvRows(capture_csv)
        rows_by_path: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            rows_by_path[str(row.get("path_id") or "").strip()].append(row)
        self.assertGreater(len(rows_by_path), 0, "format2 capture_path.csv 无有效 path")

        allowed_tail = {
            "path check period",
            "clock reconvergence pessimism",
            "clock uncertainty",
            "data required time",
        }
        for path_id, path_rows in rows_by_path.items():
            endpoint_pin = str(path_rows[0].get("endpoint") or "").strip()
            endpoint_inst = endpoint_pin.rsplit("/", 1)[0] if "/" in endpoint_pin else endpoint_pin
            points = [str(r.get("point") or "").strip() for r in path_rows]
            endpoint_idx = -1
            # 优先使用 Type=endpoint 的 CK 行，避免命中普通 pin 的同名 CK。
            for idx, row in enumerate(path_rows):
                p = str(row.get("point") or "").strip()
                t = str(row.get("Type") or "").strip().lower()
                if endpoint_inst and t == "endpoint" and p.startswith(f"{endpoint_inst}/CK"):
                    endpoint_idx = idx
                    break
            if endpoint_idx < 0:
                # 回退：若无 endpoint 类型，则取最后一个同实例 CK，保证尾部约束判断稳定。
                for idx in range(len(points) - 1, -1, -1):
                    if endpoint_inst and points[idx].startswith(f"{endpoint_inst}/CK"):
                        endpoint_idx = idx
                        break
            self.assertGreaterEqual(endpoint_idx, 0, f"path_id={path_id} 缺少 endpoint CK")

            tail_points = points[endpoint_idx + 1 :]
            self.assertGreater(len(tail_points), 0, f"path_id={path_id} endpoint CK 后无尾部约束")
            for p in tail_points:
                if p.startswith("slack ("):
                    continue
                self.assertIn(p, allowed_tail, f"path_id={path_id} 出现非法 capture 尾部行: {p}")

    def test_validation_flow_generates_report_timing_tcl(self):
        """验证 run_validation_flow 的完整回归链路与关键语义约束。"""
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

        # 1) 生成产物完整性
        for rpt in ("gen_format1.rpt", "gen_format2.rpt", "gen_pt.rpt"):
            self.assertTrue((out_dir / "reports" / rpt).is_file(), f"缺少报告文件: {rpt}")
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

        # format2 基线切换：不再输出 x/y 坐标列，Cap 后不再硬编码 xd。
        f2_report = (out_dir / "reports" / "gen_format2.rpt").read_text(encoding="utf-8")
        self.assertNotIn("x-coord", f2_report)
        self.assertNotIn("y-coord", f2_report)
        self.assertNotIn(" xd", f2_report)

        # 2) extract 产物完整性 + 基本规模一致性
        for fmt in ("format1", "format2", "pt"):
            self._assertExtractArtifacts(out_dir, fmt)
        expected_paths = 100
        for fmt in ("format1", "format2", "pt"):
            summary_rows = self._readCsvRows(out_dir / f"extract_{fmt}" / "path_summary.csv")
            self.assertEqual(len(summary_rows), expected_paths, f"{fmt} path_summary 行数异常")

        # 3) compare 统计结构完整性
        compare_dir = out_dir / "compare"
        self.assertTrue((compare_dir / "pt_vs_format1.csv").is_file(), "缺少 pt_vs_format1.csv")
        self.assertTrue((compare_dir / "pt_vs_format2.csv").is_file(), "缺少 pt_vs_format2.csv")
        self._assertCompareStats(compare_dir / "pt_vs_format1_stats.json", expected_paths)
        self._assertCompareStats(compare_dir / "pt_vs_format2_stats.json", expected_paths)
        self.assertTrue((compare_dir / "detail_pt_vs_format1" / "compare.csv").is_file(), "缺少 detail_pt_vs_format1/compare.csv")
        self.assertTrue((compare_dir / "detail_pt_vs_format2" / "compare.csv").is_file(), "缺少 detail_pt_vs_format2/compare.csv")

        # 4) format2 Derate 回归门禁（覆盖率 + 单值基线）
        self._assertFormat2DerateCoverage(out_dir)

        # 5) format2 capture 结构门禁（endpoint CK + 合法尾部）
        self._assertFormat2CaptureTail(out_dir)

        # 6) format1 capture 强约束（保留历史回归点）
        capture_csv = out_dir / "extract_format1" / "capture_path.csv"
        rows = self._readCsvRows(capture_csv)
        path1_rows = [r for r in rows if str(r.get("path_id") or "").strip() == "1"]
        points = [str(r.get("point") or "").strip() for r in path1_rows]
        endpoint_pin = str(path1_rows[0].get("endpoint") or "").strip() if path1_rows else ""
        endpoint_inst = endpoint_pin.rsplit("/", 1)[0] if "/" in endpoint_pin else endpoint_pin
        endpoint_idx = -1
        for i, p in enumerate(points):
            if endpoint_inst and p.startswith(f"{endpoint_inst}/CK"):
                endpoint_idx = i
                break
        self.assertGreaterEqual(endpoint_idx, 0, "format1 capture 缺少 endpoint CK 行")
        tail_points = points[endpoint_idx + 1 :]
        self.assertGreaterEqual(len(tail_points), 3, "endpoint CK 后的约束尾部行不足")
        self.assertEqual(tail_points[0], "path check period")
        self.assertEqual(tail_points[1], "clock reconvergence pessimism")
        self.assertEqual(tail_points[2], "clock uncertainty")


if __name__ == "__main__":
    unittest.main()
