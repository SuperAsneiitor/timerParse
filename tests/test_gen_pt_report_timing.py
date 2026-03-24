# -*- coding: utf-8 -*-
"""gen_pt_report_timing 脚本测试：through 参数依据 trigger_edge(r/f)。"""
from __future__ import annotations

import os
import csv
import argparse
import tempfile
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.gen_pt_report_timing import build_through_args, _classify_point, format_report_timing, run_gen_pt


class TestGenPtReportTiming(unittest.TestCase):
    def test_classify_by_trigger_edge_first(self):
        """当 trigger_edge 存在时，应优先按 r/f 判定 rise/fall。"""
        # 即使 pin 名是 Z（旧逻辑会判 fall），只要 trigger_edge=r 就必须是 rise
        self.assertEqual(_classify_point("u1/Z (BUF)", "r"), "rise")
        # 即使 pin 名是 A（旧逻辑会判 rise），只要 trigger_edge=f 就必须是 fall
        self.assertEqual(_classify_point("u2/A (BUF)", "f"), "fall")

    def test_build_through_args_use_trigger_edge(self):
        rows = [
            # startpoint 前的 clock 需要跳过
            {"point": "clock PTCLK (rise edge)", "point_index": "1", "trigger_edge": ""},
            # 从 startpoint 开始收集 through
            {"point": "u_start/A (BUF)", "point_index": "2", "trigger_edge": "r"},
            {"point": "u_mid/Z (BUF)", "point_index": "3", "trigger_edge": "f"},
            # 空 trigger_edge 回退旧规则：Q 判 fall
            {"point": "u_out/Q (DFF)", "point_index": "4", "trigger_edge": ""},
            # net 跳过
            {"point": "u_net (net)", "point_index": "5", "trigger_edge": "r"},
        ]
        through = build_through_args(rows, startpoint="u_start/A")
        self.assertEqual(
            through,
            [
                ("-rise_through", "u_start/A"),
                ("-fall_through", "u_mid/Z"),
                ("-fall_through", "u_out/Q"),
            ],
        )

    def test_build_through_args_startpoint_is_instance_only(self):
        """PT 风格：startpoint 为实例名，point 为 instance/pin，仍应从首引脚起收集 through。"""
        rows = [
            {"point": "clock clk (rise edge)", "point_index": "1", "trigger_edge": ""},
            {
                "point": "u_logic/path_1/U0/CK (CLKINV1)",
                "point_index": "2",
                "trigger_edge": "r",
            },
            {"point": "u_logic/path_1/U0/Z (CLKINV1) <-", "point_index": "3", "trigger_edge": "r"},
            {"point": "u_logic/path_1/n0 (net)", "point_index": "4", "trigger_edge": ""},
        ]
        through = build_through_args(
            rows,
            startpoint="u_logic/path_1/U0",
            startpoint_match="instance",
        )
        self.assertEqual(
            through,
            [
                ("-rise_through", "u_logic/path_1/U0/CK"),
                ("-rise_through", "u_logic/path_1/U0/Z"),
            ],
        )

    def test_build_through_args_exact_skips_instance_only_points(self):
        """默认 exact：startpoint 仅为实例名且 point 为 instance/pin 时不产生 through。"""
        rows = [
            {"point": "u_logic/path_1/U0/CK (CLKINV1)", "point_index": "1", "trigger_edge": "r"},
        ]
        through = build_through_args(rows, startpoint="u_logic/path_1/U0")
        self.assertEqual(through, [])

    def test_build_through_args_exact_strips_cell_on_startpoint(self):
        """format2 常在 startpoint 列带 (CELL)，与 point 列 strip 后应对齐。"""
        rows = [
            {"point": "x_top/u0/Z (BUF)", "point_index": "1", "trigger_edge": "r"},
        ]
        through = build_through_args(rows, startpoint="x_top/u0/Z (BUF)")
        self.assertEqual(through, [("-rise_through", "x_top/u0/Z")])

    def test_format_report_timing_redirect_to_output_file(self):
        """每条 report_timing 命令末尾都应追加 >> ${output_file}。"""
        cmd = format_report_timing(
            path_id=1,
            startpoint_clock="CLK_A",
            endpoint_clock="CLK_B",
            through_list=[("-rise_through", "u_start/A"), ("-fall_through", "u_mid/Z")],
            wrap=False,
        )
        self.assertIn("report_timing -from [get_clocks CLK_A] -to [get_clocks CLK_B]", cmd)
        self.assertIn("-rise_through {u_start/A}", cmd)
        self.assertIn("-fall_through {u_mid/Z}", cmd)
        self.assertIn(">> ${output_file}", cmd)

    def test_format_report_timing_redirect_no_through(self):
        """无 through 参数时也需要追加 >> ${output_file}。"""
        cmd = format_report_timing(
            path_id=2,
            startpoint_clock="",
            endpoint_clock="",
            through_list=[],
            startpoint_pin="u0/A",
            endpoint_pin="u1/Z",
            wrap=False,
        )
        self.assertIn("report_timing -from {u0/A} -to {u1/Z}", cmd)
        self.assertIn(">> ${output_file}", cmd)

    def test_run_gen_pt_uses_output_file(self):
        """当传入 args.output_file 时，TCL 里 set output_file 应指向该路径。"""
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            launch_csv = td_path / "launch_path.csv"
            tcl_path = td_path / "report_timing.tcl"
            rpt_target = td_path / "my_report.rpt"

            fieldnames = [
                "path_id",
                "startpoint",
                "endpoint",
                "startpoint_clock",
                "endpoint_clock",
                "slack",
                "slack_status",
                "point_index",
                "point",
                "trigger_edge",
            ]
            rows = [
                {
                    "path_id": "1",
                    "startpoint": "u_start/A",
                    "endpoint": "u_out/Q",
                    "startpoint_clock": "CLK_A",
                    "endpoint_clock": "CLK_B",
                    "slack": "0",
                    "slack_status": "MET",
                    "point_index": "1",
                    "point": "clock CLK_A (rise edge)",
                    "trigger_edge": "",
                },
                {
                    "path_id": "1",
                    "startpoint": "u_start/A",
                    "endpoint": "u_out/Q",
                    "startpoint_clock": "CLK_A",
                    "endpoint_clock": "CLK_B",
                    "slack": "0",
                    "slack_status": "MET",
                    "point_index": "2",
                    "point": "u_start/A (BUF)",
                    "trigger_edge": "r",
                },
                {
                    "path_id": "1",
                    "startpoint": "u_start/A",
                    "endpoint": "u_out/Q",
                    "startpoint_clock": "CLK_A",
                    "endpoint_clock": "CLK_B",
                    "slack": "0",
                    "slack_status": "MET",
                    "point_index": "3",
                    "point": "u_mid/Z (BUF)",
                    "trigger_edge": "f",
                },
                {
                    "path_id": "1",
                    "startpoint": "u_start/A",
                    "endpoint": "u_out/Q",
                    "startpoint_clock": "CLK_A",
                    "endpoint_clock": "CLK_B",
                    "slack": "0",
                    "slack_status": "MET",
                    "point_index": "4",
                    "point": "u_out/Q (DFF)",
                    "trigger_edge": "",
                },
            ]
            with open(launch_csv, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

            args = argparse.Namespace(
                launch_glob="",
                launch_csv=str(launch_csv),
                output=str(tcl_path),
                max_paths=0,
                no_wrap=False,
                extra="",
                report_file="report_file.rpt",
                output_file=str(rpt_target),
                rise_cmd="-rise_through",
                fall_cmd="-fall_through",
                startpoint_match="exact",
                jobs=1,
            )

            rc = run_gen_pt(args)
            self.assertEqual(rc, 0)

            tcl_text = tcl_path.read_text(encoding="utf-8")
            self.assertIn(f'set output_file "{rpt_target}"', tcl_text)


if __name__ == "__main__":
    unittest.main()

