from __future__ import annotations

import unittest

from lib.compare.path_detail_html import _alignRowsByPointSequence, _alignRowsForFormat1Gap, _trimCaptureSummaryTail


class TestCompareFormat1GapAlign(unittest.TestCase):
    def test_trim_capture_summary_tail(self):
        rows = [
            {"point": "x/u1/CK"},
            {"point": "path check period"},
            {"point": "clock reconvergence pessimism"},
            {"point": "clock uncertainty"},
            {"point": "data required time"},
            {"point": "slack (VIOLATED)"},
        ]
        trimmed = _trimCaptureSummaryTail(rows)
        self.assertEqual(len(trimmed), 1)
        self.assertEqual(trimmed[0].get("point"), "x/u1/CK")

    def test_insert_blank_row_for_format1_port_gap(self):
        rows_format1 = [
            {"point": "clock CORECLK (rise edge)", "Location": ""},
            {"point": "clock source latency", "Location": ""},
            {"point": "pll_cpu_clk  （propagated)", "Location": ""},
            {"point": "u/a", "Location": ""},
        ]
        rows_other = [
            {"point": "clock CORECLK (rise edge)"},
            {"point": "clock source latency"},
            {"point": "pll_cpu_clk (propagated)"},
            {"point": "pll_cpu_clk (net)"},
            {"point": "u/a"},
        ]
        g, t = _alignRowsForFormat1Gap(rows_format1, rows_other)
        self.assertEqual(len(g), len(t))
        self.assertEqual(g[3], {})

    def test_no_insert_when_short_side_is_not_format1(self):
        rows_pt_short = [
            {"point": "clock CORECLK (rise edge)"},
            {"point": "clock source latency"},
            {"point": "pll_cpu_clk  （propagated)"},
            {"point": "u/a"},
        ]
        rows_format1_long = [
            {"point": "clock CORECLK (rise edge)", "Location": ""},
            {"point": "clock source latency", "Location": ""},
            {"point": "pll_cpu_clk  （propagated)", "Location": ""},
            {"point": "dft_clk (net)", "Location": ""},
            {"point": "u/a", "Location": ""},
        ]
        g, t = _alignRowsForFormat1Gap(rows_pt_short, rows_format1_long)
        self.assertEqual(g, rows_pt_short)
        self.assertEqual(t, rows_format1_long)

    def test_point_sequence_alignment_handles_middle_insert(self):
        rows_g = [
            {"point": "clock CORECLK (rise edge)"},
            {"point": "clock source latency"},
            {"point": "pll_cpu_clk  （propagated)"},
            {"point": "dft_clk (net)"},
            {"point": "u0/I"},
            {"point": "u0/Z"},
        ]
        rows_t = [
            {"point": "clock CORECLK (rise edge)"},
            {"point": "clock source latency"},
            {"point": "pll_cpu_clk  （propagated)"},
            {"point": "u0/I"},
            {"point": "u0/Z"},
            {"point": "clock uncertainty"},
        ]
        ag, at = _alignRowsByPointSequence(rows_g, rows_t)
        self.assertEqual(len(ag), len(at))
        # dft_clk (net) 只在 G 侧存在，应在 T 侧补空
        idx_dft = next(i for i, r in enumerate(ag) if (r.get("point") or "") == "dft_clk (net)")
        self.assertEqual(at[idx_dft], {})

    def test_point_sequence_alignment_ignores_arrow_suffix(self):
        rows_g = [
            {"point": "x/path/u0/Z (INV) <-"},
            {"point": "x/path/n0 (net)"},
        ]
        rows_t = [
            {"point": "x/path/u0/Z (INV)"},
            {"point": "x/path/n0 (net)"},
        ]
        ag, at = _alignRowsByPointSequence(rows_g, rows_t)
        self.assertEqual((ag[0].get("point") or "").strip(), "x/path/u0/Z (INV) <-")
        self.assertEqual((at[0].get("point") or "").strip(), "x/path/u0/Z (INV)")


if __name__ == "__main__":
    unittest.main()
