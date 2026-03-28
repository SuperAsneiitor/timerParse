from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lib.compare.csv_path_points import loadSegmentCsvByPathId


class TestCompareCsvPathPointsAlias(unittest.TestCase):
    def test_normalize_incr_path_to_stepdelay_pathtime(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "launch.csv"
            p.write_text(
                "\n".join(
                    [
                        "path_id,point_index,point,Incr,Path",
                        "1,1,p1,0.010,0.100",
                    ]
                ),
                encoding="utf-8",
            )
            got = loadSegmentCsvByPathId(p)
            row = got["1"][0]
            self.assertEqual(row.get("StepDelay"), "0.010")
            self.assertEqual(row.get("PathTime"), "0.100")

    def test_normalize_delay_time_to_stepdelay_pathtime(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "launch.csv"
            p.write_text(
                "\n".join(
                    [
                        "path_id,point_index,point,Delay,Time",
                        "1,1,p1,0.012,0.102",
                    ]
                ),
                encoding="utf-8",
            )
            got = loadSegmentCsvByPathId(p)
            row = got["1"][0]
            self.assertEqual(row.get("StepDelay"), "0.012")
            self.assertEqual(row.get("PathTime"), "0.102")


if __name__ == "__main__":
    unittest.main()
