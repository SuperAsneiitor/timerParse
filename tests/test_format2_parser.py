# -*- coding: utf-8 -*-
"""Format2 解析器测试：y-coord、各 Type 属性、path_summary 及 point 名称完整性。"""
from __future__ import annotations

import os
import tempfile
import unittest

# 允许从项目根目录运行：python -m pytest tests/ 或 python tests/test_format2_parser.py
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.format2_parser import (
    Format2Parser,
    _desc_to_point,
    _tail_n_numeric_and_desc,
    _is_numeric_token,
)


def _test_split_derate_xy():
    """验证 Derate 列含 {x,y} 时能拆成 Derate 与 x、y（供 test_derate_xy_split 调用）。"""
    p = Format2Parser()
    derate_clean, x, y = p._split_derate_and_xy("1.100,1.100{219.156,772.737}")
    assert derate_clean == "1.100,1.100", derate_clean
    assert x == "219.156", x
    assert y == "772.737", y
    derate_clean2, x2, y2 = p._split_derate_and_xy("0.900,0.900")
    assert derate_clean2 == "0.900,0.900" and x2 == "" and y2 == "", (derate_clean2, x2, y2)


# 最小 format2 报告片段：单条 path，含 clock/port/net/pin/arrival/required/slack
MINIMAL_FORMAT2_REPORT = r"""
Path Start         :  start/Q ( flip-flop, falling edge-triggered,  CPU_CLK)
Path End           :  end/D ( flip-flop, falling edge-triggered,  CPU_CLK)

Type                            Fanout                 Cap                  D-Trans                      Trans               Derate               x-coord     y-coord         D-Delay             Delay           Time           Description
-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
clock                                                                                                                                                                                        0.000           0.000   pll_cpu_clk (rise edge)
port                                                                                                                                              {  100.0    200.0}                     0.000           0.000 / dft_clk (in)
net                                  1                  0.003 xd                                                                                                                                                     core_dft_clk
pin                                                                              -0.000                   0.000              0.900,0.900          {  219.156    772.737}       -0.000        0.000           0.000 / cell/A (BUF)
pin                                                                                                       0.017              0.900,0.900          {  219.786    772.695}                     0.033           0.034 \ cell/Z (BUF)
-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
pin                                                                              -0.000                   0.000               0.900,0.900         {  530.91     992.21}         -0.000            0.001           1.234 / end/D (FF)
arrival                                                                                                                                                                                                      1.234   data arrival time
clock                                                                                                                                                                                        0.000           0.000   clk (rise edge)
required                                                                                                                                                                                               2.000   data required time
slack                                                                                                                                                                                                 -0.766   slack (VIOLATED)
"""

# 多类型 point 名称测试：覆盖前缀、/ 与 \、长路径、多种 cell 后缀（参考 format_2.timing_report.rpt.txt）
FORMAT2_REPORT_DIVERSE_POINTS = r"""
Path Start         :  start/Q ( flip-flop, falling edge-triggered,  CPU_CLK)
Path End           :  end/D ( flip-flop, falling edge-triggered,  CPU_CLK)

Type                            Fanout                 Cap                  D-Trans                      Trans               Derate               x-coord     y-coord         D-Delay             Delay           Time           Description
-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
clock                                                                                                                                                                                        0.000           0.000   pll_cpu_clk (rise edge)
port                                                                                                                                              {  219.156    772.737}                     0.000           0.000 / dft_clk (in)
net                                  1                  0.003 xd                                                                                                                                                     core_dft_clk
net                                  2                  0.006 xd                                                                                                                                                     x_ct_top_0_coreclk
pin                                                                              -0.000                   0.000              0.900,0.900          {  219.156    772.737}       -0.000        0.000           0.000 / core_clock_x_ct_top_0_x_ct_clk_top/core_clk_buf/U2/A2 (AND2V1_96S6T16R)
pin                                                                                                       0.017              0.900,0.900          {  219.786    772.695}                     0.033           0.034 / core_clock_x_ct_top_0_x_ct_clk_top/core_clk_buf/U2/Z (AND2V1_96S6T16R)
pin                                                                              -0.000                   0.000              0.900,0.900          {  530.91     992.21}        -0.000        0.001           0.035 / x_ct_top_0_x_ct_core_x_ct_idu_top_x_ct_idu_rf_dp/x_rf_pipe6_gated_clk/x_gated_clk_cell/CK (CLKLANQV4_96S6T16L)
pin                                                                                                       0.015              0.900,0.900          {  530.91     992.21}                      0.048           0.082 \ x_ct_top_0_x_ct_core_x_ct_idu_top_x_ct_idu_rf_dp/x_rf_pipe6_gated_clk/x_gated_clk_cell/Q (CLKLANQV4_96S6T16L)
net                                  2                  0.006 xd                                                                                                                                                     x_ct_top_0_x_ct_core_x_ct_idu_top_x_ct_idu_rf_dp/rf_pipe6_clk
pin                                                                              -0.000                   0.000              0.900,0.900          {  530.91     992.21}        -0.000        0.002           0.035 / u_core_x_ct_top_0_x_ct_core_x_ct_idu_top_x_ct_idu_rf_dp/rf_pipe6_prf_srcv0_vreg_fr_reg_1_/CK (DRNQV4_96S6T16UL)
pin                                                                                                       0.013              0.900,0.900          {  530.91     992.21}                      0.052           0.082 \ u_core_x_ct_top_0_x_ct_core_x_ct_idu_top_x_ct_idu_rf_dp/rf_pipe6_prf_srcv0_vreg_fr_reg_1_/Q (DRNQV4_96S6T16UL)
pin                                                                              -0.000                   0.000              0.900,0.900          {  530.91     992.21}        -0.000        0.003           0.035 / x_ct_top_0_x_ct_core_x_ct_idu_top_x_ct_idu_rf_prf_vregfile_fr/U14830/A2 (NOR2V1_96S6T16UL)
pin                                                                                                       0.016              0.900,0.900          {  530.91     992.21}                      0.042           0.082 \ x_ct_top_0_x_ct_core_x_ct_idu_top_x_ct_idu_rf_prf_vregfile_fr/U14830/ZN (NOR2V1_96S6T16UL)
pin                                                                              -0.000                   0.000              0.900,0.900          {  530.91     992.21}        -0.000        0.001           0.035 / x_ct_top_0_x_ct_core_x_ct_vfpu_top_x_ct_vfpu_dp/U1933/A2 (AO22V1_96S6T16R)
pin                                                                                                       0.017              0.900,0.900          {  530.91     992.21}                      0.054           0.082 \ x_ct_top_0_x_ct_core_x_ct_vfpu_top_x_ct_vfpu_dp/U1933/Z (AO22V1_96S6T16R)
pin                                                                              -0.000                   0.000               0.900,0.900         {  530.91     992.21}        -0.000        0.001           1.344 / x_ct_top_0_x_ct_core_x_ct_vfpu_top_x_ct_vfpu_dp/dp_ex1_pipe6_vfpu_srcf0_reg_4_/D (DRNQV1T_96S6T16UL)
arrival                                                                                                                                                                                                      1.344   data arrival time
-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
required                                                                                                                                                                                               2.000   data required time
slack                                                                                                                                                                                                 -0.766   slack (VIOLATED)
"""

# 期望的 point 名称（与 FORMAT2_REPORT_DIVERSE_POINTS 中各行一一对应，仅保留有 point 的行）
EXPECTED_POINTS_DIVERSE = [
    "pll_cpu_clk (rise edge)",           # clock
    "dft_clk (in)",                       # port
    "core_dft_clk",                       # net
    "x_ct_top_0_coreclk",                 # net
    "core_clock_x_ct_top_0_x_ct_clk_top/core_clk_buf/U2/A2 (AND2V1_96S6T16R)",
    "core_clock_x_ct_top_0_x_ct_clk_top/core_clk_buf/U2/Z (AND2V1_96S6T16R)",
    "x_ct_top_0_x_ct_core_x_ct_idu_top_x_ct_idu_rf_dp/x_rf_pipe6_gated_clk/x_gated_clk_cell/CK (CLKLANQV4_96S6T16L)",
    "x_ct_top_0_x_ct_core_x_ct_idu_top_x_ct_idu_rf_dp/x_rf_pipe6_gated_clk/x_gated_clk_cell/Q (CLKLANQV4_96S6T16L)",
    "x_ct_top_0_x_ct_core_x_ct_idu_top_x_ct_idu_rf_dp/rf_pipe6_clk",  # net
    "u_core_x_ct_top_0_x_ct_core_x_ct_idu_top_x_ct_idu_rf_dp/rf_pipe6_prf_srcv0_vreg_fr_reg_1_/CK (DRNQV4_96S6T16UL)",
    "u_core_x_ct_top_0_x_ct_core_x_ct_idu_top_x_ct_idu_rf_dp/rf_pipe6_prf_srcv0_vreg_fr_reg_1_/Q (DRNQV4_96S6T16UL)",
    "x_ct_top_0_x_ct_core_x_ct_idu_top_x_ct_idu_rf_prf_vregfile_fr/U14830/A2 (NOR2V1_96S6T16UL)",
    "x_ct_top_0_x_ct_core_x_ct_idu_top_x_ct_idu_rf_prf_vregfile_fr/U14830/ZN (NOR2V1_96S6T16UL)",
    "x_ct_top_0_x_ct_core_x_ct_vfpu_top_x_ct_vfpu_dp/U1933/A2 (AO22V1_96S6T16R)",
    "x_ct_top_0_x_ct_core_x_ct_vfpu_top_x_ct_vfpu_dp/U1933/Z (AO22V1_96S6T16R)",
    "x_ct_top_0_x_ct_core_x_ct_vfpu_top_x_ct_vfpu_dp/dp_ex1_pipe6_vfpu_srcf0_reg_4_/D (DRNQV1T_96S6T16UL)",
]


class TestFormat2Helpers(unittest.TestCase):
    """模块级辅助函数单元测试。"""

    def test_desc_to_point_slash(self):
        self.assertEqual(_desc_to_point("0.000 / path/name"), "path/name")
        self.assertEqual(_desc_to_point(" / dft_clk (in)"), "dft_clk (in)")

    def test_desc_to_point_backslash(self):
        self.assertEqual(_desc_to_point("0.034 \\ cell/Z (BUF)"), "cell/Z (BUF)")

    def test_desc_to_point_plain(self):
        self.assertEqual(_desc_to_point("pll_cpu_clk (rise edge)"), "pll_cpu_clk (rise edge)")
        self.assertEqual(_desc_to_point("core_dft_clk"), "core_dft_clk")

    def test_tail_n_numeric_and_desc(self):
        values, desc = _tail_n_numeric_and_desc("clock 0.000 0.000 pll_cpu_clk (rise edge)", 2)
        self.assertEqual(values, ["0.000", "0.000"])
        self.assertEqual(desc, "pll_cpu_clk (rise edge)")

        values1, desc1 = _tail_n_numeric_and_desc("required 2.000 data required time", 1)
        self.assertEqual(values1, ["2.000"])
        self.assertEqual(desc1, "data required time")

    def test_is_numeric_token(self):
        self.assertTrue(_is_numeric_token("0.000"))
        self.assertTrue(_is_numeric_token("-0.253"))
        self.assertTrue(_is_numeric_token("772.737"))
        self.assertFalse(_is_numeric_token("xd"))
        self.assertFalse(_is_numeric_token("pll_cpu_clk"))

    def test_derate_xy_split(self):
        """Derate 列与坐标连写（如 1.100,1.100{219.156,772.737}）时拆成 Derate 与 x、y。"""
        _test_split_derate_xy()


class TestFormat2ParserOutput(unittest.TestCase):
    """Format2 解析结果检查：y-coord、Type 属性、path_summary。"""

    def setUp(self):
        self.parser = Format2Parser()

    def test_parse_minimal_report(self):
        """解析最小报告，检查 path 块能被正确切分并解析。"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".rpt", delete=False, encoding="utf-8") as f:
            f.write(MINIMAL_FORMAT2_REPORT)
            path = f.name
        try:
            out = self.parser.parse_report(path)
            self.assertGreater(len(out.summary_rows), 0, "应有至少一条 path summary")
            self.assertGreater(len(out.launch_rows), 0, "应有 launch 路径点")
            self.assertGreater(len(out.capture_rows), 0, "应有 capture 路径点")
        finally:
            os.unlink(path)

    def test_path_summary_columns(self):
        """path_summary 必须包含 path_id, arrival_time, required_time, slack。"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".rpt", delete=False, encoding="utf-8") as f:
            f.write(MINIMAL_FORMAT2_REPORT)
            path = f.name
        try:
            out = self.parser.parse_report(path)
            for row in out.summary_rows:
                for key in ("path_id", "arrival_time", "required_time", "slack"):
                    self.assertIn(key, row, f"summary 行应包含 {key}")
            # 最小报告中应有 arrival/required/slack 被填入
            self.assertTrue(
                any(r.get("arrival_time") for r in out.summary_rows),
                "至少一条 path 应有 arrival_time",
            )
            self.assertTrue(
                any(r.get("required_time") for r in out.summary_rows),
                "至少一条 path 应有 required_time",
            )
            self.assertTrue(
                any(r.get("slack") for r in out.summary_rows),
                "至少一条 path 应有 slack",
            )
        finally:
            os.unlink(path)

    def test_pin_and_port_have_x_and_y_coord(self):
        """含坐标的行（pin/port）必须同时有 x-coord 和 y-coord。"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".rpt", delete=False, encoding="utf-8") as f:
            f.write(MINIMAL_FORMAT2_REPORT)
            path = f.name
        try:
            out = self.parser.parse_report(path)
            pin_port_rows = [
                r for r in out.launch_rows + out.capture_rows
                if (r.get("Type") or "").strip().lower() in ("pin", "port")
            ]
            self.assertGreater(len(pin_port_rows), 0, "应有至少一行 pin 或 port")
            for row in pin_port_rows:
                x = (row.get("x-coord") or "").strip()
                y = (row.get("y-coord") or "").strip()
                self.assertTrue(x != "", f"pin/port 行应有 x-coord: {row.get('point')}")
                self.assertTrue(y != "", f"pin/port 行应有 y-coord: {row.get('point')}")
        finally:
            os.unlink(path)

    def test_net_rows_have_fanout_cap_description(self):
        """net 行应有 Fanout、Cap、Description（point）。"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".rpt", delete=False, encoding="utf-8") as f:
            f.write(MINIMAL_FORMAT2_REPORT)
            path = f.name
        try:
            out = self.parser.parse_report(path)
            net_rows = [
                r for r in out.launch_rows + out.capture_rows
                if (r.get("Type") or "").strip().lower() == "net"
            ]
            self.assertGreater(len(net_rows), 0, "应有至少一行 net")
            for row in net_rows:
                self.assertIn("Fanout", row)
                self.assertIn("Cap", row)
                self.assertIn("Description", row)
                self.assertTrue((row.get("point") or "").strip() != "", "net 应有 point 名")
        finally:
            os.unlink(path)

    def test_clock_rows_have_delay_time_description(self):
        """clock 行应有 Delay、Time、Description。"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".rpt", delete=False, encoding="utf-8") as f:
            f.write(MINIMAL_FORMAT2_REPORT)
            path = f.name
        try:
            out = self.parser.parse_report(path)
            clock_rows = [
                r for r in out.launch_rows + out.capture_rows
                if (r.get("Type") or "").strip().lower() == "clock"
            ]
            self.assertGreater(len(clock_rows), 0, "应有至少一行 clock")
            for row in clock_rows:
                self.assertIn("Delay", row)
                self.assertIn("Time", row)
                self.assertTrue((row.get("point") or "").strip() != "", "clock 应有 point 名")
        finally:
            os.unlink(path)

    def test_trigger_edge_from_slash_backslash(self):
        """format2 的 input/output pin: '/' -> r, '\\' -> f。"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".rpt", delete=False, encoding="utf-8") as f:
            f.write(MINIMAL_FORMAT2_REPORT)
            path = f.name
        try:
            out = self.parser.parse_report(path)
            pin_rows = [
                r for r in out.launch_rows + out.capture_rows
                if (r.get("Type") or "").strip().lower() in ("pin", "input_pin", "output_pin")
            ]
            self.assertGreater(len(pin_rows), 0)
            # cell/A 来自 " / "，应为 r
            row_a = next((r for r in pin_rows if "cell/A" in (r.get("point") or "")), None)
            # cell/Z 来自 " \ "，应为 f
            row_z = next((r for r in pin_rows if "cell/Z" in (r.get("point") or "")), None)
            self.assertIsNotNone(row_a)
            self.assertIsNotNone(row_z)
            self.assertEqual((row_a.get("trigger_edge") or "").strip(), "r")
            self.assertEqual((row_z.get("trigger_edge") or "").strip(), "f")
        finally:
            os.unlink(path)


class TestFormat2PointNames(unittest.TestCase):
    """Point 名称完整性：多类型、长路径、/ 与 \\、多种 cell 后缀，无前后截断。"""

    def setUp(self):
        self.parser = Format2Parser()

    def test_diverse_point_names_match_expected(self):
        """解析含多种 point 的报告，逐行校验 point 与预期一致（无截断）。"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".rpt", delete=False, encoding="utf-8") as f:
            f.write(FORMAT2_REPORT_DIVERSE_POINTS)
            path = f.name
        try:
            out = self.parser.parse_report(path)
            launch_points = [r.get("point", "").strip() for r in out.launch_rows]
            self.assertGreaterEqual(
                len(launch_points), len(EXPECTED_POINTS_DIVERSE),
                "launch 行数应不少于预期 point 数",
            )
            for i, expected in enumerate(EXPECTED_POINTS_DIVERSE):
                self.assertLess(i, len(launch_points), f"缺少第 {i+1} 行 launch point")
                self.assertEqual(
                    launch_points[i],
                    expected,
                    f"第 {i+1} 行 point 与预期不符（可能被截断）",
                )
        finally:
            os.unlink(path)

    def test_pin_point_no_leading_truncation(self):
        """含 ' / ' 或 ' \\ ' 的 pin 行：point 不应丢失前缀（不能以 _ct_ 开头表示被截断）。"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".rpt", delete=False, encoding="utf-8") as f:
            f.write(FORMAT2_REPORT_DIVERSE_POINTS)
            path = f.name
        try:
            out = self.parser.parse_report(path)
            pin_rows = [
                r for r in out.launch_rows + out.capture_rows
                if (r.get("Type") or "").strip().lower() in ("input_pin", "output_pin", "pin")
            ]
            self.assertGreater(len(pin_rows), 0, "应有 pin 行")
            # 若 point 以 _ct_ 开头，说明 path 前缀被截断（如 core_clock_ 或 x_ 丢失）
            bad = [r for r in pin_rows if (r.get("point") or "").strip().startswith("_ct_")]
            self.assertEqual(len(bad), 0, "pin point 不应因列对齐丢失前缀而变成 _ct_ 开头")
        finally:
            os.unlink(path)

    def test_pin_point_cell_suffix_complete(self):
        """pin 行 cell 后缀应完整（如 CLKLANQV4_96S6T16L），不能截成 CLK 或 CLKL。"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".rpt", delete=False, encoding="utf-8") as f:
            f.write(FORMAT2_REPORT_DIVERSE_POINTS)
            path = f.name
        try:
            out = self.parser.parse_report(path)
            launch_points = [r.get("point", "").strip() for r in out.launch_rows]
            # 应出现完整 cell 类型名
            full_cells = ["CLKLANQV4_96S6T16L", "DRNQV4_96S6T16UL", "NOR2V1_96S6T16UL", "AO22V1_96S6T16R", "DRNQV1T_96S6T16UL"]
            for cell in full_cells:
                found = any(cell in p for p in launch_points)
                self.assertTrue(found, f"应有含完整 cell 后缀的 point: {cell}")
        finally:
            os.unlink(path)


class TestFormat2ParserWithRealFile(unittest.TestCase):
    """使用真实报告文件（若存在）做集成检查。"""

    def setUp(self):
        self.report_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "input", "format_2.timing_report.rpt.txt",
        )

    def test_real_file_if_present(self):
        """若 input/format_2.timing_report.rpt.txt 存在，解析并检查 y-coord 与 path_summary。"""
        if not os.path.isfile(self.report_path):
            self.skipTest("报告文件不存在，跳过集成测试")
        parser = Format2Parser()
        out = parser.parse_report(self.report_path)
        self.assertGreater(len(out.summary_rows), 0)
        pin_port = [
            r for r in out.launch_rows + out.capture_rows
            if (r.get("Type") or "").strip().lower() in ("pin", "port")
        ]
        self.assertGreater(len(pin_port), 0)
        missing_y = [r for r in pin_port if not (r.get("y-coord") or "").strip()]
        self.assertEqual(len(missing_y), 0, "所有 pin/port 行都应有 y-coord")

    def test_real_file_pin_points_not_truncated(self):
        """真实报告中 pin 的 point 不得以 _ct_ 开头（即不能丢 core_clock_ 等前缀）。"""
        if not os.path.isfile(self.report_path):
            self.skipTest("报告文件不存在，跳过集成测试")
        parser = Format2Parser()
        out = parser.parse_report(self.report_path)
        pin_rows = [
            r for r in out.launch_rows + out.capture_rows
            if (r.get("Type") or "").strip().lower() in ("input_pin", "output_pin", "pin")
        ]
        # 若报告中有 core_clock_ 开头的路径，解析后不应变成 _ct_ 开头
        bad = [r for r in pin_rows if (r.get("point") or "").strip().startswith("_ct_")]
        self.assertEqual(len(bad), 0, "pin point 不应丢失前缀而变成 _ct_ 开头")


if __name__ == "__main__":
    unittest.main()
