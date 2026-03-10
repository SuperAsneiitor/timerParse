# -*- coding: utf-8 -*-
"""gen_pt_report_timing 脚本测试：through 参数依据 trigger_edge(r/f)。"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.gen_pt_report_timing import build_through_args, _classify_point, format_report_timing


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


if __name__ == "__main__":
    unittest.main()

