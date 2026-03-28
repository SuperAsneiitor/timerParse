"""parser_V2 数据模型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PointRecord:
    """单个 point 行的标准化结构。"""

    point: str
    point_type: str
    attrs: dict[str, Any] = field(default_factory=dict)
    raw_line: str = ""


@dataclass
class PathRecord:
    """单条 timing path 的结构化结果。"""

    path_id: int
    meta: dict[str, Any] = field(default_factory=dict)
    launch_points: list[PointRecord] = field(default_factory=list)
    capture_points: list[PointRecord] = field(default_factory=list)


@dataclass
class ParseResult:
    """整份报告解析结果。"""

    format_name: str
    paths: list[PathRecord] = field(default_factory=list)
