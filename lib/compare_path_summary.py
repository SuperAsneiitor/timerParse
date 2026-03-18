"""向后兼容：CLI 入口 + 单测/脚本使用的 compare/load_summary/compute_stats。"""
from __future__ import annotations

from typing import List

from .compare import run_compare_path_summary
from .compare.path_summary_compare import compareRows, load_summary
from .compare.stats import compute_stats


def run_compare(args) -> int:
    return run_compare_path_summary(args)


def compare(golden_rows: List[dict], test_rows: List[dict]) -> List[dict]:
    """按 path_id 对齐（与单测、旧用法一致）。"""
    return compareRows(golden_rows, test_rows, match_by="path_id")
