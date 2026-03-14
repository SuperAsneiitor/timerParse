#!/usr/bin/env python3
"""薄包装：调用 lib 统一入口的 compare 子命令。"""
from __future__ import annotations

import os
import sys

# 从 scripts/ 运行时保证可导入 lib
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from lib.cli import run_cli

if __name__ == "__main__":
    sys.exit(run_cli(["compare"] + sys.argv[1:]))
