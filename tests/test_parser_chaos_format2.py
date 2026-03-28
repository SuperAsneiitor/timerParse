"""parser_chaos format2 语义解析测试。"""
from __future__ import annotations

import unittest

from lib.parser_V2.format2_parser import Format2Parser


def _buildPath(net_line: str) -> str:
    return (
        "Path Start         :  start/Q ( flip-flop, falling edge-triggered,  CPU_CLK)\n"
        "Path End           :  end/D ( flip-flop, falling edge-triggered,  CPU_CLK)\n"
        "\n"
        "Type                            Fanout                 Cap                  D-Trans                      Trans               Derate               x-coord     y-coord         D-Delay             Delay           Time           Description\n"
        "-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------\n"
        "clock                                                                                                                                                                                        0.000           0.000   pll_cpu_clk (rise edge)\n"
        f"{net_line}\n"
        "arrival                                                                                                                                                                                                      1.234   data arrival time\n"
        "required                                                                                                                                                                                               2.000   data required time\n"
        "slack                                                                                                                                                                                                 -0.766   slack (VIOLATED)\n"
    )


class TestParserChaosFormat2(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = Format2Parser()

    def testNetWithXd(self):
        _meta, launch_rows, _capture_rows = self.parser.parseOnePath(
            1,
            _buildPath("net                                  1                  0.003 xd                                                                                                                                                     core_dft_clk"),
        )
        net = next(r for r in launch_rows if (r.get("Type") or "").strip().lower() == "net")
        self.assertEqual((net.get("Cap") or "").strip(), "0.003")
        self.assertEqual((net.get("point") or "").strip(), "core_dft_clk")

    def testNetWithXf(self):
        _meta, launch_rows, _capture_rows = self.parser.parseOnePath(
            1,
            _buildPath("net                                  1                  0.003 xf                                                                                                                                                     core_dft_clk"),
        )
        net = next(r for r in launch_rows if (r.get("Type") or "").strip().lower() == "net")
        self.assertEqual((net.get("Cap") or "").strip(), "0.003")
        self.assertEqual((net.get("point") or "").strip(), "core_dft_clk")

    def testNetWithNoUnit(self):
        _meta, launch_rows, _capture_rows = self.parser.parseOnePath(
            1,
            _buildPath("net                                  1                  0.003                                                                                                                                                        core_dft_clk"),
        )
        net = next(r for r in launch_rows if (r.get("Type") or "").strip().lower() == "net")
        self.assertEqual((net.get("Cap") or "").strip(), "0.003")
        self.assertEqual((net.get("point") or "").strip(), "core_dft_clk")


if __name__ == "__main__":
    unittest.main()
