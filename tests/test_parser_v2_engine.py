import unittest

from lib.parser import TimingParserV2


SAMPLE = """
Startpoint: u_top/U0/CK
Endpoint: u_top/U9/D
Path Group: clk_main
Path Type: max

Point                                    Incr       Path
------------------------------------------------------------
clock clk_main (rise edge)               0.010      0.010
u_top/U0/CK (DFF)                        0.030      0.040
net 1 0.003 xd u_top/n1
u_top/U9/A (DFF)                         0.020      0.060
u_top/U9/D (DFF)                         0.040      0.100
data arrival time                                   0.100
clock clk_main (rise edge)               0.050      0.150
required time                                      0.200
slack (MET)                                        0.050
""".strip()


class TestParserV2Engine(unittest.TestCase):
    def test_parse_format2_basic(self):
        parser = TimingParserV2("format2")
        result = parser.parse_text(SAMPLE)
        self.assertEqual(result.format_name, "format2")
        self.assertEqual(len(result.paths), 1)
        path = result.paths[0]
        self.assertEqual(path.meta.get("startpoint"), "u_top/U0/CK")
        self.assertEqual(path.meta.get("endpoint"), "u_top/U9/D")
        self.assertGreaterEqual(len(path.launch_points), 3)
        self.assertGreaterEqual(len(path.capture_points), 2)

    def test_parse_type_and_attrs(self):
        parser = TimingParserV2("format2")
        path = parser.parse_text(SAMPLE).paths[0]
        net_rows = [r for r in path.launch_points if r.point_type == "net"]
        self.assertEqual(len(net_rows), 1)
        self.assertEqual(net_rows[0].attrs.get("Fanout"), "1")
        self.assertEqual(net_rows[0].attrs.get("Cap"), "0.003")
        self.assertEqual(net_rows[0].attrs.get("CapUnit"), "xd")
        self.assertEqual(net_rows[0].point, "u_top/n1")

    def test_net_cap_unit_xf(self):
        parser = TimingParserV2("format2")
        sample_xf = SAMPLE.replace(" xd ", " xf ")
        path = parser.parse_text(sample_xf).paths[0]
        net_rows = [r for r in path.launch_points if r.point_type == "net"]
        self.assertEqual(len(net_rows), 1)
        self.assertEqual(net_rows[0].attrs.get("Cap"), "0.003")
        self.assertEqual(net_rows[0].attrs.get("CapUnit"), "xf")
        self.assertEqual(net_rows[0].point, "u_top/n1")


if __name__ == "__main__":
    unittest.main()
