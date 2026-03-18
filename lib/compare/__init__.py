from __future__ import annotations

"""
比较模块入口。

目前只提供基于 path_summary.csv 的路径级对比：
- 读入 golden/test 两侧的 path_summary.csv
- 按 path_id 对齐（后续可扩展为按 startpoint/endpoint 对齐）
- 计算 arrival/required/slack 以及 launch/data 段 delay、clock pessimism/uncertainty 等差异
- 输出对比 CSV、统计 JSON/CSV、HTML 报告与图表。

CLI 层仍通过 lib.compare_path_summary.run_compare 暴露子命令入口。
"""

from .path_summary_compare import run_compare_path_summary

__all__ = ["run_compare_path_summary"]

