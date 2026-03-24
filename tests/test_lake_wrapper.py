from __future__ import annotations

import os
import unittest
from pathlib import Path


class TestLakeWrapper(unittest.TestCase):
    def test_lake_bin_preserves_argv_boundaries(self):
        """lake wrapper 必须使用 $argv:q，避免 --extra 的带空格参数被二次拆分。"""
        repo_root = Path(__file__).resolve().parents[1]
        lake_bin = repo_root / "tools" / "lake" / "bin" / "lake"
        self.assertTrue(lake_bin.is_file(), "lake 可执行脚本不存在")

        text = lake_bin.read_text(encoding="utf-8")
        self.assertIn(
            'exec $py -m lib "$cmd" $argv:q',
            text,
            "lake 转发命令必须使用 $argv:q 来保留参数边界",
        )


if __name__ == "__main__":
    unittest.main()
